#!/usr/bin/env python3

import argparse
import sys
import os
import logging
import json
import time
import math

# This makes sure we can import from the top level magellan package.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir)))

from magellan import index, utils
from elasticsearch.exceptions import ElasticsearchException
from elasticsearch import RequestsHttpConnection
from datetime import timedelta
from requests_aws4auth import AWS4Auth

if __name__ == "__main__":
    # Setup a logger that emits JSON
    json_handler = logging.StreamHandler(sys.stdout)
    json_handler.setFormatter(utils.StackdriverJsonFormatter())
    handlers = [ json_handler ]
    logging.basicConfig(
        level=os.environ.get('LOG_LEVEL', default=logging.INFO),
        handlers=handlers
    )
    logger = logging.getLogger(__name__)

    # Setup the CLI
    parser = argparse.ArgumentParser(prog="magellan")

    # These parameters are relevant to all commands.
    parser.add_argument("--host", type=str, default="localhost")
    parser.add_argument("-p", "--port", type=int, default=9200)
    parser.add_argument("-s", "--secure", action="store_true")
    parser.add_argument("-a", "--auth-type", type=str, required=False, default=None, choices=["basic", "aws"])
    parser.add_argument("-c", "--creds", type=str, default=None, help="Path to a credentials file")
    parser.add_argument("--profile", type=str, default=None,
        help="A connection profile to use. If specified --port, --host and --secure are ignored.")

    cmds = parser.add_subparsers(dest="cmd")

    index_names = [ idx.name for idx in index.ALL_INDICES ]

    # The init command sets up the required indices on a cluster
    init = cmds.add_parser("init", help="Initialize a new search index.")
    init.add_argument("-o", "--only", type=str, choices=index_names, default=None,
        help="If specified, only the provided index is initialized.")

    # The load command indexes data
    load = cmds.add_parser("load", help="Load data into the search index.")
    load.add_argument("data", type=str, help="Path to the directory containing data to load.")
    load.add_argument("-b", "--batch-size", type=int,
        default=100,
        help="The size of each batch. Set this higher to make things faster, and lower if index requests are timing out.")
    load.add_argument("-o", "--only", type=str, choices=index_names, default=None)

    # The search command executes a query string query.
    search = cmds.add_parser("search",
        help="Execute a query string query against the search index. " +
             "See: https://www.elastic.co/guide/en/elasticsearch/reference/current/query-dsl-query-string-query.html")
    search.add_argument("query", type=str, help="A search query to execute")
    search.add_argument("-s", "--size", type=int, help="The maximum number of results to return.", default=10)
    search.add_argument("-p", "--pretty", help="Nicely format the output", action="store_true", default=False)

    # The stats command returns cluster wide statistics
    stats = cmds.add_parser("stats", help="Returns cluster statistics as JSON.")

    # Delete all cluster data
    delete = cmds.add_parser("delete", help="Deletes all data from the search index.")
    delete.add_argument("-o", "--only", type=str, choices=index_names, default=None)

    args = parser.parse_args()

    # Check if the profile is set. If set, we load the configuration from `profiles.json`,
    # where the connection details for commonly used clusters are defined.
    if args.profile:
        with open(os.path.join(os.path.dirname(__file__), os.pardir, "profiles.json")) as fh:
            profiles = json.load(fh)
            profile = profiles[args.profile]
            if profile is None:
                logger.error(f"Profile not found {args.profile}")
                sys.exit(1)
            host = profile.get("host")
            port = profile.get("port")
            secure = profile.get("secure")
            auth_type = profile.get("auth_type")
    else:
        host = args.host
        port = args.port
        secure = args.secure
        auth_type = args.auth_type

    # If the auth type is set, but creds aren't set complain
    if auth_type is not None and args.creds is None:
        logger.error("The --creds argument is required if the --auth-type argument is set.")
        sys.exit(1)

    # Setup the appropriate client, based upon authentication settings
    if args.creds is not None:
        with open(args.creds, "r") as fh:
            creds = json.load(fh)
            if auth_type == "basic":
                client = index.Client(
                    [ host ],
                    http_auth=(creds["username"], creds["password"]),
                    use_ssl=secure,
                    verify_certs=secure,
                    port=port
                )
            elif auth_type == "aws":
                auth = AWS4Auth(creds["access_key"], creds["secret_key"], creds["region"], "es")
                client = index.Client(
                    [ host ],
                    http_auth=auth,
                    use_ssl=secure,
                    port=port,
                    verify_certs=secure,
                    connection_class=RequestsHttpConnection
                )
            else:
                logger.error(f"Unknown auth type: {auth_type}")
                sys.exit(1)
    else:
        client = index.Client(
            [ host ],
            use_ssl=secure,
            verify_certs=secure,
            port=port
        )

    if args.cmd == "init":
        try:
            indices = [ idx for idx in index.ALL_INDICES if idx.name == args.only or args.only is None ]
            client.create_indices(indices)
            logger.info("Cluster setup complete")
            sys.exit(0)
        except ElasticsearchException as err:
            logger.error(err)
    elif args.cmd == "load":
        try:
            now = time.perf_counter()
            types_to_load = set([ args.only or idx.name for idx in index.ALL_INDICES ])
            if index.PAPER.name in types_to_load:
                total_papers = client.bulk_index_papers_from_path(args.data, batch_size=args.batch_size)
            else:
                total_papers = 0
            if index.METADATA.name in types_to_load:
                metadata_file_path = os.path.join(args.data, "metadata.csv")
                total_metadata_entries = client.bulk_index_metadata_from_file(metadata_file_path,
                    batch_size=args.batch_size)
            else:
                total_metadata_entries = 0
            # TODO: Find a third party library for formatting durations.
            elapsed = time.perf_counter() - now
            delta = timedelta(seconds=elapsed)
            mins = math.floor(delta.total_seconds() / 60)
            seconds = delta.total_seconds() - mins * 60
            logger.info(
                f"Loaded {total_papers} papers and {total_metadata_entries} metadata entries in " +
                f"{mins}m{round(seconds)}s"
            )
            sys.exit(0)
        except ElasticsearchException as err:
            logger.error(err)
    elif args.cmd == "search":
        try:
            results = client.search(
                body={
                    "query": {
                        "query_string": {
                            "query": args.query
                        }
                    }
                },
                size=args.size
            )
            if not args.pretty:
                print(json.dumps(results))
            else:
                for hit in results["hits"]["hits"]:
                    source = hit["_source"]
                    print("---")
                    print(f"ID: {source['paper_id']}")
                    print(f"Title: {source['metadata']['title']}")
                    authors = []
                    for author in source["metadata"]["authors"]:
                        authors.append(f"{author['first']} {author['last']}")
                    print(f"Authors: {', '.join(authors)}")
                    print(f"Abstract:")
                    abstract = [ a["text"] for a in source["abstract"] ]
                    print("\n".join(abstract))
            sys.exit(0)
        except ElasticsearchException as err:
            logger.error(err)
    elif args.cmd == "stats":
        try:
            stats = client.indices.stats()
            print(json.dumps(stats))
            sys.exit(0)
        except ElasticsearchException as err:
            logger.error(err)
    elif args.cmd == "delete":
        indices = [ idx for idx in index.ALL_INDICES if idx.name == args.only or args.only is None ]
        to_delete = ", ".join([ idx.name for idx in indices ])
        confirm = input(f"This will delete all data in indices: {to_delete}, are you sure [y|n]? ")
        if confirm != "y":
            logger.info("No action taken")
            sys.exit(0)
        try:
            client.delete_indices(indices)
        except ElasticsearchException as err:
            logger.error(err)
