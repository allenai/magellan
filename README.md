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

## Getting Started

1. First download the [CORD-19 dataset](https://pages.semanticscholar.org/coronavirus-research) to
   your local machine.

2. Then start a local Elasticsearch instance like so:

    ```
    ./bin/elasticsearch start
    ```

    The cluster will run in the background on your local machine, listening on ports `9200` and `9300`.

    You can stop the cluster at any time by running:

    ```
    ./bin/elasticsearch stop
    ```

3. Next, initialize the index:

    ```
    python -m magellan init
    ```

4. Finally, load the data into the index:

    ```
    python magellan load
    ```

  It takes about 5 minutes to load the the data into a local index. It takes
  about an hour to populate a remote one. We'll make that faster in the near
  term.

Your local elasticsearch cluster's data is wiped everytime it's restarted, so you'll need to
reexecute the steps above to repopulate the index after doing so.

## Explore the Data

You can use [Santiago](https://github.com/allenai/santiago) to run a local UI for issuing full-text
queries against the cluster.

## Contributions

We welcome and encourage contributions. Please don't hesitate to submit a pull request.

## Getting Help

Don't hesitate to ask questions or propose ideas in the [CORD-19 Discourse](https://discourse.cord-19.semanticscholar.org/).

You can also submit bugs or feature proposals [here](https://github.com/allenai/magellan/issues).
