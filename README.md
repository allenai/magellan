# Magellan

A CLI for loading the [CORD-19](https://pages.semanticscholar.org/coronavirus-research) dataset into an 
Elasticsearch cluster.

## Prerequisites

* [python3](https://python.org)
* [miniconda](https://docs.conda.io/en/latest/miniconda.html)

## One Time Setup

* Setup a a conda environment:

    ```
    conda create -n magellan python=3.8
    conda activate magellan
    ```

* Install dependencies:

    ```
    python -m pip install -r requirements.txt
    ```

## Usage

First download the [CORD-19 dataset](https://pages.semanticscholar.org/coronavirus-research) to
your local machine.

If you'd like to use a local cluster, you can start one like so:

```
./bin/elasticsearch start
```

The cluster will run in the background on your local machine, listening on ports `9200` and `9300`.
You can stop the cluster via:

```
./bin/elasticsearch stop
```

Be aware that the local cluster's data is wiped everytime it restarts.

## Setting Up a New Cluster

If you've just created a cluster, you'll want to start by creating the required search indices
via the `init` command:

```
python -m magellan --profile local init
```

Next, you can populate it with data by running. Replace `data/` with the path to your local version
of the CORD-19 dataset.

```
python -m magellan --profile local load data/
```

Once that's complete, you can execute simple queries like so:

```
python -m magellan --profile local search COVID --pretty
```

If you omit the `--pretty` option raw JSON will be emitted, you can use [`jq`](https://stedolan.github.io/jq/) to process the
data:

```
python -m magellan --profile local search "COVID transmission rates" | \
    jq '.hits.hits[]._source | { title: .metadata.title, id: .paper_id, abstract: .abstract[].text }'
```

## Getting Help

Send a note to [sams@allenai.org](mailto:sams@allenai.org) if you'd like help using this tool.
