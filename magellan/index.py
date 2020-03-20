import os
import logging
import json

from typing import List
from dataclasses import dataclass
from elasticsearch import Elasticsearch

@dataclass
class Index:
    name: str
    version: str

    def fqn(self):
        """
        Returns the fully qualified index name, which includes both the index name and
        version.
        """
        return f"{self.name}_{self.version}"

    def config_path(self) -> str:
        # TODO: Parameterize the root path.
        return os.path.abspath(os.path.join(
            os.path.dirname(__file__),
            os.path.pardir,
            "config",
            "index",
            self.version,
            f"{self.name}.json"))

# Static mapping of indices. For now there's only one.
PAPER = Index("paper", "v1")

class Client(Elasticsearch):
    def create_indices(self) -> None:
        """
        Initialize the search index by creating the required search indices.
        """
        indices = [ PAPER ]
        for idx in indices:
            config_path = idx.config_path()
            with open(config_path, "r") as fh:
                config = json.load(fh)
                self.indices.create(index=PAPER.fqn(), body=config)

    def bulk_index_papers(self, papers: List[dict]) -> None:
        """
        Bulk indexes a list of papers.
        """
        logger = logging.getLogger(__name__)
        body = []
        for p in papers:
            # The _id field is Elasticsearch's document identifier. If we don't provide one
            # an identifier will be generated. We use our paper ids instead.
            body.append(json.dumps({ "index": { "_id": p["paper_id"] } }))
            body.append(json.dumps(p))
        # This ensures the body is terminated by a closing newline
        body.append("")
        logger.info(f"Bulk indexing {len(papers)} papers")
        self.bulk(index=PAPER.fqn(), body=body, timeout="60s", request_timeout=60)

    def bulk_index_papers_from_path(self, path: str, batch_size: int) -> int:
        """
        Bulk index papers at the specified path. Each paper should be stored in a single
        JSON file.
        """
        logger = logging.getLogger(__name__)
        batch = []
        total = 0
        for (dirpath, dirs, files) in os.walk(path):
            for f in files:
                _, ext = os.path.splitext(f)
                if ext == ".json":
                    [ _, collection ] = os.path.split(dirpath)
                    full_path = os.path.join(dirpath, f)
                    logger.debug(f"loading {full_path}")
                    with open(full_path, "r") as fh:
                        paper = json.load(fh)
                        # The data is separated into directories, each of which we call a
                        # collection. We append that info to each paper so we can filter
                        # by collection.
                        paper["collection"] = collection
                        batch.append(paper)
                        if len(batch) == batch_size:
                            self.bulk_index_papers(batch)
                            total += len(batch)
                            batch = []
        if len(batch) > 0:
            self.bulk_index_papers(batch)
            total += len(batch)
        return total
