# (C) Copyright 2020 ECMWF.
#
# This software is licensed under the terms of the Apache Licence Version 2.0
# which can be obtained at http://www.apache.org/licenses/LICENSE-2.0.
# In applying this licence, ECMWF does not waive the privileges and immunities
# granted to it by virtue of its status as an intergovernmental organisation
# nor does it submit to any jurisdiction.
#

import datetime
import itertools
import logging
from warnings import warn

import numpy as np

from climetlab.decorators import cached_method, normalize
from climetlab.indexing.cube import index_to_coords
from climetlab.readers.grib.index import FieldSet
from climetlab.utils.dates import to_datetime

LOG = logging.getLogger(__name__)


class ConstantMaker:
    def __init__(self, field):
        self.field = field
        self.shape = self.field.shape

    @property
    def resolution(self):
        return self.field.resolution

    @cached_method
    def grid_points(self):
        return self.field.grid_points()

    @cached_method
    def ecef_xyz(self):
        # https://en.wikipedia.org/wiki/Geographic_coordinate_conversion#From_geodetic_to_ECEF_coordinates
        # We assume that the Earth is a sphere of radius 1 so N(phi) = 1
        # We assume h = 0

        lat, lon = self.grid_points()

        phi = np.deg2rad(lat)
        lda = np.deg2rad(lon)

        cos_phi = np.cos(phi)
        cos_lda = np.cos(lda)
        sin_phi = np.sin(phi)
        sin_lda = np.sin(lda)

        x = cos_phi * cos_lda
        y = cos_phi * sin_lda
        z = sin_phi

        return x, y, z

    @cached_method
    def latitude_(self):
        return self.grid_points()[0]

    def latitude(self, date):
        return self.latitude_()

    @cached_method
    def cos_latitude_(self):
        return np.cos(np.deg2rad(self.grid_points()[0]))

    def cos_latitude(self, date):
        return self.cos_latitude_()

    @cached_method
    def sin_latitude_(self):
        return np.sin(np.deg2rad(self.grid_points()[0]))

    def sin_latitude(self, date):
        return self.sin_latitude_()

    @cached_method
    def longitude_(self):
        return self.grid_points()[1]

    def longitude(self, date):
        return self.longitude_()

    @cached_method
    def cos_longitude_(self):
        return np.cos(np.deg2rad(self.grid_points()[1]))

    def cos_longitude(self, date):
        return self.cos_longitude_()

    @cached_method
    def sin_longitude_(self):
        return np.sin(np.deg2rad(self.grid_points()[1]))

    def sin_longitude(self, date):
        return self.sin_longitude_()

    def ecef_x(self, date):
        return self.ecef_xyz()[0]

    def ecef_y(self, date):
        return self.ecef_xyz()[1]

    def ecef_z(self, date):
        return self.ecef_xyz()[2]

    def julian_day(self, date):
        date = to_datetime(date)
        delta = date - datetime.datetime(date.year, 1, 1)
        julian_day = delta.days + delta.seconds / 86400.0
        return np.full((np.prod(self.field.shape),), julian_day)

    def cos_julian_day(self, date):
        radians = self.julian_day(date) / 365.25 * np.pi * 2
        return np.cos(radians)

    def sin_julian_day(self, date):
        radians = self.julian_day(date) / 365.25 * np.pi * 2
        return np.sin(radians)

    def local_time(self, date):
        lon = self.longitude(date)
        date = to_datetime(date)
        delta = date - datetime.datetime(date.year, date.month, date.day)
        hours_since_midnight = (delta.days + delta.seconds / 86400.0) * 24
        return (lon / 360.0 * 24.0 + hours_since_midnight) % 24

    def cos_local_time(self, date):
        radians = self.local_time(date) / 24 * np.pi * 2
        return np.cos(radians)

    def sin_local_time(self, date):
        radians = self.local_time(date) / 24 * np.pi * 2
        return np.sin(radians)

    def insolation(self, date):
        warn(
            "The function `insolation` is deprecated, please use `cos_solar_zenith_angle` instead"
        )
        return self.cos_solar_zenith_angle(date)

    def toa_incident_solar_radiation(self, date):
        from earthkit.meteo.solar import toa_incident_solar_radiation

        date = to_datetime(date)
        result = toa_incident_solar_radiation(
            date - datetime.timedelta(minutes=30),
            date + datetime.timedelta(minutes=30),
            self.latitude_(),
            self.longitude_(),
            intervals_per_hour=2,
        )
        return result.flatten()

    def cos_solar_zenith_angle(self, date):
        from earthkit.meteo.solar import cos_solar_zenith_angle

        date = to_datetime(date)
        result = cos_solar_zenith_angle(
            date,
            self.latitude_(),
            self.longitude_(),
        )
        return result.flatten()


class ConstantField:
    def __init__(
        self,
        maker,
        date,
        param,
        proc,
        number=None,
    ):
        self.maker = maker
        self.date = date
        self.param = param
        self.number = number
        self.proc = proc
        self._metadata = dict(
            valid_datetime=date if isinstance(date, str) else date.isoformat(),
            param=param,
            level=None,
            levelist=None,
            number=number,
            levtype=None,
        )

    @property
    def resolution(self):
        return self.maker.resolution

    @property
    def shape(self):
        return self.maker.shape

    def grid_points(self):
        return self.maker.grid_points()

    def to_numpy(self, reshape=True, dtype=None):
        values = self.proc(self.date)
        if reshape:
            values = values.reshape(self.shape)
        if dtype is not None:
            values = values.astype(dtype)

        # assert len(values.shape) == 1, (self, self.name, reshape, dtype, values.shape)
        return values

    def __repr__(self):
        return "ConstantField(%s,%s,%s)" % (
            self.param,
            self.date,
            self.number,
        )

    def metadata(self, name):
        return self._metadata[name]


def make_datetime(date, time):
    if time is None:
        return date
    if date.hour or date.minute:
        raise ValueError(
            f"Duplicate information about time time={time}, and time={date.hour}:{date.minute} from date={date}"
        )
    assert date.hour == 0, (date, time)
    assert date.minute == 0, (date, time)
    assert str(time).isdigit(), (type(time), time)
    time = int(time)
    if time > 24:
        time = time // 100
    return datetime.datetime(date.year, date.month, date.day, time)


class Constants(FieldSet):
    def __init__(self, source_or_dataset, request={}, **kwargs):
        request = dict(**request)
        request.update(kwargs)

        self.request = self._request(**request)

        def find_numbers(source_or_dataset):
            if "number" in self.request:
                return self.request["number"]

            assert hasattr(
                source_or_dataset, "unique_values"
            ), f"{source_or_dataset} (type '{type(source_or_dataset).__name__}') is not a proper source or dataset"

            return source_or_dataset.unique_values(
                "number", patches={"number": {None: 0}}
            )["number"]

        def find_dates(source_or_dataset):
            if "date" not in self.request and "time" in self.request:
                raise ValueError("Cannot specify time without date")

            if "date" in self.request and "time" not in self.request:
                return self.request["date"]

            if "date" in self.request and "time" in self.request:
                dates = [
                    make_datetime(date, time)
                    for date, time in itertools.product(
                        self.request["date"], self.request["time"]
                    )
                ]
                assert len(set(dates)) == len(dates), "Duplicates dates in constants."
                return dates

            assert "date" not in self.request and "time" not in self.request
            assert hasattr(
                source_or_dataset, "unique_values"
            ), f"{source_or_dataset} (type '{type(source_or_dataset).__name__}') is not a proper source or dataset"

            return source_or_dataset.unique_values("valid_datetime")["valid_datetime"]

        self.dates = find_dates(source_or_dataset)

        self.params = self.request["param"]
        if not isinstance(self.params, (tuple, list)):
            self.params = [self.params]

        # self.numbers = self.request.get("number", [None])
        self.numbers = find_numbers(source_or_dataset)
        if not isinstance(self.numbers, (tuple, list)):
            self.numbers = [self.numbers]

        self.maker = ConstantMaker(field=source_or_dataset[0])
        self.procs = {param: getattr(self.maker, param) for param in self.params}
        self._len = len(self.dates) * len(self.params) * len(self.numbers)

    @normalize("date", "date-list")
    @normalize("time", "int-list")
    @normalize("number", "int-list")
    def _request(self, **request):
        return request

    def __len__(self):
        return self._len

    def _getitem(self, i):
        if i >= self._len:
            raise IndexError(i)

        date, param, number = index_to_coords(
            i, (len(self.dates), len(self.params), len(self.numbers))
        )

        # assert repeat == 0, "Not implemented"

        date = self.dates[date]
        # assert isinstance(date, datetime.datetime), (date, type(date))
        param = self.params[param]
        number = self.numbers[number]

        return ConstantField(
            self.maker,
            date,
            param,
            self.procs[param],
            number=number,
        )


source = Constants
