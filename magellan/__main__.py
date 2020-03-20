#!/usr/bin/env python3

import argparse
import sys
import os
import logging
import json

# This makes sure we can import from the top level magellan package.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir)))

from magellan import index, utils
from elasticsearch.exceptions import ElasticsearchException

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
    parser.add_argument("-c", "--creds", type=str, default=None, help="Path to a credentials file")

    cmds = parser.add_subparsers(dest="cmd")

    # The init command sets up the required indices on a cluster
    init = cmds.add_parser("init", help="Initialize a new search index.")

    # The load command indexes data
    load = cmds.add_parser("load", help="Load data into the search index.")
    load.add_argument("-d", "--data", type=str, help="Path to the directory containing data to load.")

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

    args = parser.parse_args()

    # If the user specified a credentials file, attempt to load them. We load them from a
    # file so that they're not passed as command line arguments which get cached in a user's
    # shell history.
    http_auth = None
    if args.creds is not None:
        with open(args.creds, "r") as fh:
            creds = json.load(fh)
            http_auth = (creds["username"], creds["password"])

    # Every command uses a client for interacting with the cluster.
    client = index.Client(
        [ args.host ],
        http_auth=http_auth,
        scheme="https" if args.secure else "http",
        port=args.port
    )

    if args.cmd == "init":
        try:
            client.create_indices()
            logger.info("Cluster setup complete")
            sys.exit(0)
        except ElasticsearchException as err:
            logger.error(err)
    elif args.cmd == "load":
        try:
            total = client.bulk_index_papers_from_path(args.data)
            logger.info(f"Loaded {total} total papers")
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
        confirm = input("This will delete all data, are you sure [y|n]? ")
        if confirm != "y":
            logger.info("No action taken")
            sys.exit(0)
        try:
            client.indices.delete(index=index.PAPER.fqn())
            logger.info(f"Deleted {index.PAPER.fqn()}")
        except ElasticsearchException as err:
            logger.error(err)
