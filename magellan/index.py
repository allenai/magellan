import os
import logging
import json
import csv

from typing import List, Optional
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
            f"{self.name}.json"
        ))

# Static mapping of indices. For now there's only one.
PAPER = Index("paper", "v1")
METADATA = Index("metadata", "v1")
ALL_INDICES = [ PAPER, METADATA ]

class Client(Elasticsearch):
    def create_indices(self, indices: List[Index] = ALL_INDICES) -> None:
        """
        Initializes the provided list of indices.
        """
        for idx in indices:
            config_path = idx.config_path()
            with open(config_path, "r") as fh:
                config = json.load(fh)
                self.indices.create(index=idx.fqn(), body=config)

    def update_mappings(self, indices: List[Index] = ALL_INDICES) -> None:
        for idx in indices:
            config_path = idx.config_path()
            with open(config_path, "r") as fh:
                config = json.load(fh)
                self.indices.put_mapping(index=idx.fqn(), body=config["mappings"])

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

    def bulk_index_metadata(self, metadata: List[dict]) -> None:
        """
        Bulk indexes a list of metadata entries.
        """
        logger = logging.getLogger(__name__)
        body = []
        for m in metadata:
            # The _id field is Elasticsearch's document identifier. If we don't provide one
            # an identifier will be generated. We use our paper ids instead.
            body.append(json.dumps({ "index": {} }))
            body.append(json.dumps(m))
        # This ensures the body is terminated by a closing newline
        body.append("")
        logger.info(f"Bulk indexing {len(metadata)} metadata entries")
        self.bulk(index=METADATA.fqn(), body=body, timeout="60s", request_timeout=60)

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

    def bulk_index_metadata_from_file(self, file_path: str, batch_size: int) -> int:
        """
        Bulk index metadata entries from the provided csv file.
        """
        batch = []
        total = 0
        with open(file_path, "r") as fh:
            for row in csv.reader(fh):
                entry = {
                    "cord_uid": row[0],
                    "paper_ids": [ pid.strip() for pid in row[1].split(";") ],
                    "source": row[2],
                    "title": row[3],
                    "doi": row[4],
                    "pmcid": row[5],
                    "pubmed_id": row[6],
                    "license": row[7],
                    "abstract": row[8],
                    "publish_time": row[9],
                    "authors": [ a.strip() for a in row[10].split(";") ],
                    "journal": row[11],
                    "msft_academic_id": row[12],
                    "who_covidence_number": row[13],
                    "has_full_text": True if row[14] == "True" else False,
                    "collection": row[15],
                    "url": row[16]
                }
                batch.append(entry)
                if len(batch) == batch_size:
                    self.bulk_index_metadata(batch)
                    total += len(batch)
                    batch = []
        if len(batch) > 0:
            self.bulk_index_metadata(batch)
            total += len(batch)
        return total

    def delete_indices(self, indices: List[Index] = ALL_INDICES) -> None:
        """
        Deletes the provided indices. Defaults to deleting all indices. Be careful, as this
        cannot be reversed.
        """
        for idx in indices:
            self.indices.delete(index=idx.fqn())
        logging.getLogger(__name__).info(f"Deleted {idx.fqn()}")
