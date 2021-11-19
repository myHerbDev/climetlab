#!/usr/bin/env python3

# (C) Copyright 2020 ECMWF.
#
# This software is licensed under the terms of the Apache Licence Version 2.0
# which can be obtained at http://www.apache.org/licenses/LICENSE-2.0.
# In applying this licence, ECMWF does not waive the privileges and immunities
# granted to it by virtue of its status as an intergovernmental organisation
# nor does it submit to any jurisdiction.
#

import os
import time

from climetlab import load_source
from climetlab.core.statistics import collect_statistics, retrieve_statistics
from climetlab.datasets import Dataset
from climetlab.decorators import normalize
from climetlab.indexing import GlobalIndex, PerUrlIndex

BASEURL = "https://storage.ecmwf.europeanweather.cloud/benchmark-dataset"

# index file has been created with :
# climetlab index_gribs --baseurl "https://storage.ecmwf.europeanweather.cloud/benchmark-dataset" \
#           data/ana/pressure/EU_analysis_pressure_params_1997-01.grb > eumetnet.index
# climetlab index_gribs --baseurl "https://storage.ecmwf.europeanweather.cloud/benchmark-dataset" \
#           data/ana/pressure/EU_analysis_pressure_params_1997-02.grb >> eumetnet.index
filename = os.path.join(os.path.dirname(__file__), "eumetnet.index")
GLOBAL_INDEX = GlobalIndex(filename, baseurl=BASEURL)


CML_BASEURL = "https://storage.ecmwf.europeanweather.cloud/climetlab"

CML_BASEURL = "https://datastore.copernicus-climate.eu/climetlab"

PER_URL_INDEX = PerUrlIndex(
    CML_BASEURL
    + "/test-data/input/eumetnet-sample/EU_analysis_pressure_params_{year}-{nn}.grb"
    # + "/test-data/input/indexed-urls/large_grib_{n}.grb"
)


def test_eumetnet_1():
    class A:
        @normalize(
            "param",
            ["133", "157", "130", "131", "132", "129"],
            aliases="eumetnet_aliases.yaml",
            multiple=True,
        )
        def __init__(self, option="abc", **request):
            self.request = request

    a = A(param="q")
    assert a.request["param"] == ["133"]
    a = A(param=133)
    assert a.request["param"] == ["133"]
    a = A(param=["q", "r"])
    assert a.request["param"] == ["133", "157"]


def test_eumetnet_2():
    class Eumetnet(Dataset):
        @normalize(
            "param",
            ["133", "157", "130", "131", "132", "129"],
            aliases="eumetnet_aliases.yaml",
            multiple=True,
        )
        def __init__(self, option="abc", **request):
            self.source = load_source("indexed-urls", GLOBAL_INDEX, request)

    a = Eumetnet(
        **{
            "domain": "g",
            "levtype": "pl",
            "levelist": "850",
            "date": "19970228",
            "time": "2300",
            "step": "0",
            "param": "r",  # "param": "157",
            "class": "ea",
            "type": "an",
            "stream": "oper",
            "expver": "0001",
        }
    )
    ds = a.to_xarray()
    assert abs(ds["r"].mean() - 49.86508560180664) < 1e-6


def test_eumetnet_3():
    class Eumetnet(Dataset):
        @normalize(
            "param",
            ["133", "157", "130", "131", "132", "129"],
            aliases="eumetnet_aliases.yaml",
            # multiple=True,
        )
        def __init__(self, option="abc", **request):
            self.source = load_source("indexed-urls", PER_URL_INDEX, request)

    a = Eumetnet(
        **{
            "domain": "g",
            "levtype": "pl",
            "levelist": "850",
            "date": "19970228",
            "time": "2300",
            "step": "0",
            "param": "r",  # "param": "157",
            "class": "ea",
            "type": "an",
            "stream": "oper",
            "expver": "0001",
            #
            "year": "1997",
            "nn": ["01", "02"],
        }
    )
    ds = a.to_xarray()
    assert abs(ds["r"].mean() - 49.86508560180664) < 1e-6


def retrieve_and_check(index, request, **kwargs):
    print("--------")
    parts = index.lookup_request(request)
    print("range_method", kwargs.get("range_method", None))
    print("REQUEST", request)
    for url, p in parts:
        total = len(index.get_backend(url).entries)
        print(f"PARTS: {len(p)}/{total} parts in {url}")

    now = time.time()
    s = load_source("indexed-urls", index, request, **kwargs)
    elapsed = time.time() - now
    print("ELAPSED", elapsed)
    try:
        paths = [s.path]
    except AttributeError:
        paths = [p.path for p in s.sources]

    for path in paths:
        # check that the downloaded gribs match the request
        for grib in load_source("file", path):
            for k, v in request.items():
                assert str(grib._get(k)) == str(v), (grib._get(k), v)
    return elapsed


def test_global_index():

    index = GlobalIndex(
        f"{CML_BASEURL}/test-data/input/indexed-urls/global_index.index",
        baseurl=f"{CML_BASEURL}/test-data/input/indexed-urls",
    )

    request = dict(param="157")
    retrieve_and_check(index, request)


def test_per_url_index():
    index = PerUrlIndex(
        f"{CML_BASEURL}/test-data/input/indexed-urls/large_grib_1.grb",
    )
    request = dict(param="157")
    retrieve_and_check(index, request)


def dev():

    index = PerUrlIndex(
        f"{CML_BASEURL}/test-data/input/indexed-urls/large_grib_1.grb",
    )

    request = dict(param="157")
    retrieve_and_check(index, request)

    request = dict(param="157", time="1000")
    retrieve_and_check(index, request)

    request = dict(date="19970101")
    retrieve_and_check(index, request)

    request = dict(param="157", time="1000", date="19970101")
    retrieve_and_check(index, request)


def dev2():
    index = PerUrlIndex(
        f"{CML_BASEURL}/test-data/input/indexed-urls/large_grib_1.grb",
    )
    collect_statistics(True)
    request = dict(param="157")

    retrieve_and_check(
        index,
        request,
        range_method="sharp(1,1)",
        force=True,
    )

    retrieve_and_check(
        index,
        request,
        range_method="cluster(100)",
        force=True,
    )

    retrieve_and_check(
        index,
        request,
        range_method="cluster(5)",
        force=True,
    )

    retrieve_and_check(
        index,
        request,
        range_method="auto",
        force=True,
    )

    retrieve_and_check(
        index,
        request,
        range_method="cluster(5)|debug|blocked(4096)|debug",
        force=True,
    )

    retrieve_and_check(
        index,
        request,
        range_method="cluster(1)",
        force=True,
    )

    for s in retrieve_statistics():
        print(s)


def timing():
    index = PerUrlIndex(
        f"{CML_BASEURL}/test-data/input/indexed-urls/large_grib_1.grb",
    )

    sizes = ["sharp", None, "auto", "cluster"]
    for r in range(11, 24):  # from 2k to 8M
        sizes.append(2 ** r)

    report = {}
    for request in [
        dict(param="157"),
        dict(param="157", time="1000"),
        dict(date="19970101"),
        dict(param="157", time="1000", date="19970101"),
    ]:
        times = []
        for n in sizes:
            elapsed = retrieve_and_check(index, request, range_method=n, force=True)
            if n is None:
                n = 0
            if n == "auto":
                n = -1
            if n == "cluster":
                n = 1
            if n == "sharp":
                n = -2
            times.append((round(elapsed * 10) / 10.0, n))

        report[tuple(request.items())] = request, sorted(times)

    for k, v in report.items():
        print(k)
        print(v)


if __name__ == "__main__":
    dev2()
    # timing()
    # from climetlab.testing import main

    # main(__file__)
