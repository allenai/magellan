import requests
import os
import logging
import json
import math
import base64

from typing import Optional, List
from dataclasses import dataclass

class Error(RuntimeError):
    index_name: str
    details: dict
    def __init__(self, index_name: str, message: str, details: dict):
        self.index_name = index_name
        self.details = details
        super().__init__(message)

class CreateIndexError(IndexError):
    def __init__(self, index_name: str, details: dict):
        super().__init__(index_name, f"Error creating index {index_name}", details)

class QueryError(RuntimeError):
    details: dict
    def __init__(self, message: str, details: dict):
        self.details = details
        super().__init__(message)

class BulkIndexError(Error):
    doc_ids: List[str]
    def __init__(self, index_name: str, doc_ids: List[str], details: dict):
        self.doc_ids = doc_ids
        super().__init__(index_name, f"Error bulk indexing papers", details)

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

@dataclass
class Client():
    host: str
    port: int
    secure: bool = False
    username: Optional[str] = None
    password: Optional[str] = None

    def cluster_url(self) -> str:
        """
        Returns a URL for the cluster.
        """
        proto = "https" if self.secure else "http"
        return f"{proto}://{self.host}:{self.port}"

    def index_url(self, idx: Index) -> str:
        """
        Returns a URL for the specified index.
        """
        proto = "https" if self.secure else "http"
        return f"{self.cluster_url()}/{idx.fqn()}"

    def auth_header(self) -> dict:
        """
        Returns the appropriate 'Authorization' header. If no credentials are associated with
        the client an empty dict is returned.
        """
        if self.username is None or self.password is None:
            return {}
        creds = f"{self.username}:{self.password}".encode("utf-8")
        token = base64.b64encode(creds).decode("utf-8")
        return { "Authorization": f"Basic {token}" }

    def create_indices(self):
        """
        Initialize the search index by creating the required search indices.
        """
        indices = [ PAPER ]
        for idx in indices:
            config_path = idx.config_path()
            with open(config_path, "r") as fh:
                config = json.load(fh)
                url = self.index_url(idx)
                resp = requests.put(url, json=config, headers=self.auth_header())
                if resp.status_code != requests.codes.ok:
                    raise CreateIndexError(idx.fqn(), resp.json())

    def bulk_index_papers(self, papers: List[dict]):
        """
        Bulk indexes a list of papers.
        """
        body = []
        for p in papers:
            # The _id field is Elasticsearch's document identifier. If we don't provide one
            # an identifier will be generated. We use our paper ids instead.
            body.append(json.dumps({ "index": { "_id": p["paper_id"] } }))
            body.append(json.dumps(p))
        # This ensures the body is terminated by a closing newline
        body.append("")
        headers = { "Content-Type": "application/x-ndjson", **self.auth_header() }
        url = f"{self.index_url(PAPER)}/_bulk"
        resp = requests.post(url, data="\n".join(body), headers=headers)
        if resp.status_code != 200 and resp.status_code != 201:
            raise BulkIndexError(PAPER.fqn(), [ p["paper_id"] for p in papers ], resp.json())

    def bulk_index_papers_from_path(self, path: str, batch_size: int = 1000) -> int:
        """
        Bulk index papers at the specified path. Each paper should be stored in a single
        JSON file.
        """
        batch = []
        total = 0
        for f in os.listdir(path):
            _, ext = os.path.splitext(f)
            if ext == ".json":
                with open(os.path.join(path, f), "r") as fh:
                    paper = json.load(fh)
                    batch.append(paper)
                    if len(batch) == batch_size:
                        self.bulk_index_papers(batch)
                        total += len(batch)
                        batch = []
        if len(batch) > 0:
            self.bulk_index_papers(batch)
            total += len(batch)
        return total

    def search(self, query: str, size: int) -> Optional[dict]:
        """
        Executes a query string query against the cluster.
        See: https://www.elastic.co/guide/en/elasticsearch/reference/current/query-dsl-query-string-query.html
        """
        url = f"{self.cluster_url()}/_search"
        resp = requests.get(url, params={ "q": query, "size": size }, headers=self.auth_header())
        if resp.status_code != requests.codes.ok:
            raise QueryError(f"Error executing query: {query}", resp.json())
        return resp.json()

    def stats(self):
        """
        Returns cluster statistics.
        """
        url = f"{self.cluster_url()}/_stats"
        resp = requests.get(url, params={ "human": "true" }, headers=self.auth_header())
        if resp.status_code != requests.codes.ok:
            raise Error(PAPER.fqn(), f"Error retrieving stats", resp.json())
        return resp.json()
