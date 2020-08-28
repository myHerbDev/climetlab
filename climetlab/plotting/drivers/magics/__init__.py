# (C) Copyright 2020 ECMWF.
#
# This software is licensed under the terms of the Apache Licence Version 2.0
# which can be obtained at http://www.apache.org/licenses/LICENSE-2.0.
# In applying this licence, ECMWF does not waive the privileges and immunities
# granted to it by virtue of its status as an intergovernmental organisation
# nor does it submit to any jurisdiction.
#

import os
import sys

from climetlab.data import load as load_data
from climetlab.core.caching import temp_file
from climetlab.core.ipython import Image, SVG

from Magics import macro

# Examples of Magics macros:
# https://github.com/ecmwf/notebook-examples/tree/master/visualisation

NONE = object()


class Action:
    action = None

    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def __repr__(self):
        return "macro.%s(%s)" % (self.action, self.kwargs)

    def execute(self):
        return getattr(macro, self.action)(**self.kwargs).execute()


class MCont(Action):
    action = "mcont"


class MCoast(Action):
    action = "mcoast"


class MMap(Action):
    action = "mmap"


class MGrib(Action):
    action = "mgrib"


class MNetcdf(Action):
    action = "mnetcdf"


class MInput(Action):
    action = "minput"


class MTable(Action):
    action = "mtable"


class MText(Action):
    action = "mtext"


class Output(Action):
    action = "output"


class Driver:
    def __init__(self, options=None):
        self._options = options if options else {}
        self._used_options = set()

        grid = self.option("grid", False)

        self._projection = None
        self._data = None
        self._width_cm = 10.0
        self._height_cm = 10.0

        self._page_ratio = 1.0
        self._contour = MCont(contour_automatic_setting="ecmwf", legend=False)

        self._grid = grid
        self._background = MCoast(
            map_grid=self._grid,
            map_grid_colour="tan",
            map_label=False,
            map_boundaries=True,
            map_coastline_land_shade=True,
            map_coastline_land_shade_colour="cream",
            map_coastline_colour="tan",
            map_grid_frame=True,
            map_grid_frame_thickness=5,
        )

        self._foreground = MCoast(
            map_grid=self._grid,
            map_label=False,
            map_grid_frame=True,
            map_grid_frame_thickness=5,
        )

        self._legend = None
        self._title = None

        self.bounding_box(90, -180, -90, 180)
        self._tmp = []

    def temp_file(self, extension=".tmp"):
        self._tmp.append(temp_file(extension))
        return self._tmp[-1].path

    def bounding_box(self, north, west, south, east):
        assert north > south, "North (%s) must be greater than south (%s)" % (
            north,
            south,
        )
        assert west != east

        self._projection = MMap(
            subpage_upper_right_longitude=float(east),
            subpage_upper_right_latitude=float(north),
            subpage_lower_left_latitude=float(south),
            subpage_lower_left_longitude=float(west),
            subpage_map_projection="cylindrical",
        )
        self._page_ratio = (north - south) / (east - west)

    def plot_grib(self, path, offset):
        self._data = MGrib(
            grib_input_file_name=path,
            grib_file_address_mode="byte_offset",
            grib_field_position=int(offset),
        )

    def plot_netcdf(self, path, variable, dimensions={}):
        dimension_setting = ["%s:%s" % (k, v) for k, v in dimensions.items()]

        if dimension_setting:
            params = dict(
                netcdf_filename=path,
                netcdf_value_variable=variable,
                netcdf_dimension_setting=dimension_setting,
                netcdf_dimension_setting_method="index",
            )
        else:
            params = dict(netcdf_filename=path, netcdf_value_variable=variable)

        self._data = MNetcdf(**params)

    def plot_numpy(
        self, data, north, west, south_north_increment, west_east_increment, metadata
    ):
        self._data = MInput(
            input_field=data,
            input_field_initial_latitude=float(north),
            input_field_latitude_step=-float(south_north_increment),
            input_field_initial_longitude=float(west),
            input_field_longitude_step=float(west_east_increment),
            input_metadata=metadata,
        )

    def plot_xarray(self, ds, variable, dimensions={}):
        tmp = self.temp_file(".nc")
        ds.to_netcdf(tmp)
        self.plot_netcdf(tmp, variable, dimension_settings)

    def plot_csv(self, path, variable):
        self._data = MTable(
            table_filename=path,
            table_latitude_variable="1",
            table_longitude_variable="2",
            table_value_variable="3",
            table_header_row=0,
            table_variable_identifier_type="index",
        )
        self.style("red-markers")

    def plot_pandas(self, frame, lat, lon, variable):
        tmp = self.temp_file(".csv")
        frame[[lat, lon, variable]].to_csv(tmp, header=False, index=False)
        self.plot_csv(tmp, variable)

    def _apply(self, collection, value, action, default_attribute=None):

        if value is None:
            return None

        if isinstance(value, dict):
            return action(value)

        if isinstance(value, str):

            data = load_data(collection, value, fail=default_attribute is None)
            if data is None:
                return action({default_attribute: value})

            magics = data["magics"]
            actions = list(magics.keys())
            assert len(actions) == 1, actions

            action = getattr(macro, actions[0])
            return action(magics[actions[0]])

        assert False, (collection, value)

    def projection(self, projection):
        if projection:
            self._projection = self._apply(
                "projections", projection, macro.mmap, "subpage_map_projection"
            )

    def style(self, style):
        if style:
            self._contour = self._apply("styles", style, macro.mcont)

    def plot_values(self, latitudes, longitudes, values, metadata={}):
        self._data = MInput(
            input_type="geographical",
            input_values=list(values),
            input_latitudes_list=list(latitudes),
            input_longitudes_list=list(longitudes),
            input_metadata=metadata,
        )

    def option(self, name, default=NONE):
        self._used_options.add(name)
        if default is NONE:
            return self._options[name]
        else:
            return self._options.get(name, default)

    def show(self):

        self.style(self.option("style", None))
        self.projection(self.option("projection", None))

        title = self.option("title", None)
        width = self.option("width", 680)
        frame = self.option("frame", False)

        path = self.option("path", self.temp_file("." + self.option("format", "png")))

        _title_height_cm = 0
        if title:
            _title_height_cm = 0.7
            if title is True:
                # Automatic title
                self._title = macro.mtext()
            else:
                self._title = macro.mtext(
                    text_lines=[str(title)],
                    # text_justification='center',
                    # text_font_size=0.6,
                    # text_mode="positional",
                    # text_box_x_position=5.00,
                    # text_box_y_position=18.50,
                    # text_colour='charcoal'
                )

        base, fmt = os.path.splitext(path)
        output = Output(
            output_formats=[fmt[1:]],
            output_name_first_page_number=False,
            page_x_length=self._width_cm,
            page_y_length=self._height_cm * self._page_ratio,
            super_page_x_length=self._width_cm,
            super_page_y_length=self._height_cm * self._page_ratio + _title_height_cm,
            subpage_x_length=self._width_cm,
            subpage_y_length=self._height_cm * self._page_ratio,
            subpage_x_position=0.0,
            subpage_y_position=0.0,
            output_width=width,
            page_frame=frame,
            page_id_line=False,
            output_name=base,
        )

        unused = set(self._options.keys()) - self._used_options
        if unused:
            print(
                "WARNING: unused argument%s:" % ("s" if len(unused) > 1 else "",),
                ", ".join("%s=%s" % (x, self._options[x]) for x in unused),
                file=sys.stderr,
            )

        args = [
            x
            for x in (
                output,
                self._projection,
                self._background,
                self._data,
                self._contour,
                self._foreground,
                self._legend,
                self._title,
            )
            if x is not None
        ]

        try:
            macro.plot(*args)
        except Exception:
            print(args, file=sys.stderr)
            raise

        if fmt == ".svg":
            Display = SVG
        else:
            Display = Image

        return Display(path, metadata=dict(width=width))
