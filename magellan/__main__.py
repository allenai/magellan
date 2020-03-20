#!/usr/bin/env python3

import argparse
import sys
import os
import logging
import json

# This makes sure we can import from the top level magellan package.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir)))

from magellan import index, utils

def print_error(err: index.Error) -> None:
    """
    Helper for printing errors encountered while performing operations against the index.
    """
    logger.error({ "message": str(err), **err.details })

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
    init = cmds.add_parser("init")

    # The load command indexes data
    load = cmds.add_parser("load")
    load.add_argument("-d", "--data", type=str, help="Path to the directory containing data to load.")

    # The search command executes a query string query.
    search = cmds.add_parser("search")
    search.add_argument("query", type=str, help="A search query to execute")
    search.add_argument("-s", "--size", type=int, help="The maximum number of results to return.", default=10)
    search.add_argument("-p", "--pretty", help="Nicely format the output", action="store_true", default=False)

    # The stats command returns cluster wide statistics
    stats = cmds.add_parser("stats")

    args = parser.parse_args()

    # If the user specified a credentials file, attempt to load them. We load them from a
    # file so that they're not passed as command line arguments which get cached in a user's
    # shell history.
    username = None
    password = None
    if args.creds is not None:
        with open(args.creds, "r") as fh:
            creds = json.load(fh)
            username = creds["username"]
            password = creds["password"]

    # Every command uses a client for interacting with the cluster.
    client = index.Client(args.host, args.port, secure=args.secure, username=username,
            password=password)

    if args.cmd == "init":
        try:
            client.create_indices()
            logger.info("Cluster initialization complete")
        except index.Error as err:
            print_error(err)
    elif args.cmd == "load":
        try:
            total = client.bulk_index_papers_from_path(args.data)
            logger.info(f"Loaded {total} papers")
        except index.Error as err:
            print_error(err)
    elif args.cmd == "search":
        try:
            results = client.search(args.query, args.size)
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
        except index.Error as err:
            print_error(err)
    elif args.cmd == "stats":
        try:
            print(json.dumps(client.stats()))
        except index.Error as err:
            print_error(err)
