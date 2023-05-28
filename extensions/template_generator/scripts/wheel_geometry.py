from math import radians, cos, sin, pi
import os
from io import BytesIO
import json
import pprint
import sys

from PIL import Image
from cairo import SVGSurface, FillRule, Context


class WheelTemplate(object):
    # Parts of the wheel
    RIM = 1
    HUB = 2
    LUG_NUTS = 3
    SPOKES = 4

    # Definition of all arguments and their default values
    ALL_ARGS = dict(
        rim_diameter=17.0,  # float, inch ["]
        rim_width=1.0,  # float, inch ["]
        hub_diameter=5.0,  # float, inch ["]
        hub_width=2.0,  # float, inch ["]
        lug_nut_count=5,  # int
        lug_nut_diameter=0.8,  # float, inch ["]
        bolt_circle_diameter=2.5,  # float, inch ["], Distance between wheel center and lug nut center
        spoke_count=5,  # int, Divided evenly along the bolt circle
        spoke_central_angle=10.0,  # float, Degrees (pie slice width)
        required_coverage_area=0.5,  # float, Solid area out of the total wheel area
        canvas_size=(512, 512)  # set (x-size, y-size), in pixels
    )

    def __init__(self, *args, **kwargs):
        """
        Params are as defined by ALL_ARGS
        """
        # Go over arguments, assign defaults where missing, and do very basic sanity checks
        self._dict = {}
        for i, (arg, default_value) in enumerate(self.ALL_ARGS.items()):
            ivalue = None
            if len(args) > i:
                ivalue = args[i]
            kwvalue = kwargs.get(arg, None)
            if ivalue is None:
                if kwvalue is None:
                    # Not given, use default
                    value = default_value
                else:
                    # Given as keyword argument
                    value = kwvalue
            elif kwvalue is None:
                # Given as positional argument
                value = ivalue
            else:
                # Given both as positional and keyword argument,
                # so raise an exception just like python would in this case
                raise TypeError("got multiple values for argument '%s'" % arg)

            if arg == "canvas_size":
                w, h = value
                if not (w > 0 and h > 0):
                    raise Exception("Canvas width/height must be positive")
            elif arg == "required_coverage_area":
                if not (0 <= value <= 1.0):
                    raise Exception("Required coverage area must be in range [0, 1]")
            elif not (value > 0):
                raise Exception("Argument '%s' must be positive" % arg)

            self._dict[arg] = value
            setattr(self, arg, value)

    @property
    def rim_radius(self):
        return self.rim_diameter / 2.0

    @property
    def rim_inner_radius(self):
        return self.rim_radius - self.rim_width

    @property
    def hub_radius(self):
        return self.hub_diameter / 2.0

    @property
    def hub_inner_radius(self):
        return self.hub_radius - self.hub_width

    @property
    def lug_nut_radius(self):
        return self.lug_nut_diameter / 2.0

    @property
    def bolt_circle_radius(self):
        return self.bolt_circle_diameter / 2.0

    def check_errors_in_geometry(self):
        """
        Check for all possible geometric contradictions in the template.
        Returns (list of error strong, set of parts that had errors)
        """
        errors = []
        err_parts = set()

        # --- Rim ---
        if self.rim_inner_radius < 0:
            errors.append("Rim width larger than its radius")
            err_parts.add(self.RIM)

        # --- Hub ---
        if self.hub_inner_radius < 0:
            errors.append("Hub width larger than its radius")
            err_parts.add(self.HUB)

        if self.hub_radius > self.rim_inner_radius:
            errors.append("Hub overlaps with rim")
            err_parts.add(self.HUB)

        # --- Lug nuts ---
        if self.lug_nut_diameter > self.hub_width:
            errors.append("Lug nut is too big to fit in hub")
            err_parts.add(self.LUG_NUTS)
        elif not (
                self.hub_inner_radius + self.lug_nut_radius <= self.bolt_circle_radius <= self.hub_radius - self.lug_nut_radius):
            errors.append("Lug nut doesn't fit in hub")
            err_parts.add(self.LUG_NUTS)

        if self.lug_nut_diameter > 2 * self.bolt_circle_radius * sin(radians(360 / self.lug_nut_count / 2.0)):
            errors.append("Lug nuts overlap each other on the bolt circle")
            err_parts.add(self.LUG_NUTS)

        # --- Spokes ---
        if self.spoke_central_angle > 360.0 / self.spoke_count:
            errors.append("Spokes overlap")
            err_parts.add(self.SPOKES)

        return errors, err_parts

    def validate_geometry(self):
        errors, err_parts = self.check_errors_in_geometry()
        if errors:
            raise Exception("; ".join(errors))

    @staticmethod
    def _floats_equal(a, b):
        return abs(a - b) < 1e-4

    @staticmethod
    def _circle_area(r):
        return pi * r ** 2

    def calc_areas(self):
        wheel_area = self._circle_area(self.rim_radius)
        rim_area = wheel_area - self._circle_area(self.rim_inner_radius)
        rim_coverage = rim_area / wheel_area
        lug_nut_area = self._circle_area(self.lug_nut_radius)
        lug_nuts_area = lug_nut_area * self.lug_nut_count
        center_bore_area = self._circle_area(self.hub_inner_radius)
        hub_area = self._circle_area(self.hub_radius) - center_bore_area - lug_nuts_area
        hub_coverage = hub_area / wheel_area
        rim_deadzone_area = pi * (self.rim_inner_radius ** 2 - self.hub_radius ** 2)
        spoke_area = rim_deadzone_area * self.spoke_central_angle / 360.0
        spokes_area = spoke_area * self.spoke_count
        spokes_coverage = spokes_area / wheel_area
        solid_area = rim_area + hub_area + spokes_area
        solid_coverage = solid_area / wheel_area

        assert self._floats_equal(solid_coverage,
                                  rim_coverage + hub_coverage + spokes_coverage), "internal geometric error1"
        assert self._floats_equal(solid_area + rim_deadzone_area - spokes_area + lug_nuts_area + center_bore_area,
                                  wheel_area), "internal geometric error2"

        def perc(f):
            return round(f * 100, 1)

        def area(f):
            return round(f, 3)

        res = {
            "wheel_area": area(wheel_area),
            "solid_area": area(solid_area),
            "coverage": perc(solid_coverage),

            "rim_area": area(rim_area),
            "hub_area": area(hub_area),
            "spokes_area": area(spokes_area),

            "rim_coverage": perc(rim_coverage),
            "hub_coverage": perc(hub_coverage),
            "spokes_coverage": perc(spokes_coverage),

            "rim_solid_coverage": perc(rim_area / solid_area),
            "hub_solid_coverage": perc(hub_area / solid_area),
            "spokes_solid_coverage": perc(spokes_area / solid_area),
        }
        return res

    def to_dict(self):
        return dict(self._dict)


class WheelTemplateRenderer:
    DRAW_NUTS_AS_HUB_HOLES = True
    """
    True - The lug nuts will be produced as hollow circles during the filling of the hub ring. 
           This is the best option because it keeps the background color of the holes.
    False - The lug nuts will be rendered as white circles on top of the fully solid hub ring.
    """
    SCENE_RIM_MARGIN = 1.2  # How much to make the scene (The rendered space) larger than the wheel rim
    LUG_NUTS_INITIAL_ANGLE = 0.0
    SPOKES_INITIAL_ANGLE = 20.0

    BLACK = (0.0, 0.0, 0.0)
    WHITE = (1.0, 1.0, 1.0)
    RED = (1.0, 0.0, 0.0)
    DEFAULT_COLOR = BLACK
    ERROR_COLOR = RED

    def __init__(self, wt):
        assert isinstance(wt, WheelTemplate), "'wt' must be instance of WheelTemplate'"
        self._wt = wt
        self._ctx = None  # Temporary cairo drawing context
        self._err_parts = []  # Temporary list of wheel parts that have geometric errors and should be highlighted

        # Both width and height of the scene, in inches. It is slightly larger than the wheel rim
        # This is unaffected by the canvas resolution and aspect ratio.
        self._scene_length = self.rim_diameter * self.SCENE_RIM_MARGIN

        self._canvas_w, self._canvas_h = self.canvas_size
        self._x_pixels_per_inch = self._canvas_w / self._scene_length
        self._y_pixels_per_inch = self._canvas_h / self._scene_length

    def __getattr__(self, key):
        return getattr(self._wt, key)

    def _get_part_color(self, part):
        if part in self._err_parts:
            return self.ERROR_COLOR
        else:
            return None

    def _set_color(self, color=None):
        color = color or self.DEFAULT_COLOR
        self._ctx.set_source_rgb(*color)

    def _set_color_for_part(self, part):
        self._set_color(self._get_part_color(part))

    def _prepare_ring_path(self, radius, width):
        ctx = self._ctx
        ctx.arc(0, 0, radius, 0, radians(360))
        ctx.new_sub_path()
        # Need to make it negative so that the fill works.
        # An alternative way is to call ctx.set_fill_rule(FillRule.EVEN_ODD)
        ctx.arc_negative(0, 0, max(0, radius - width), radians(360), 0)

    def _draw_ring(self, radius, width):
        self._prepare_ring_path(radius, width)
        self._ctx.fill()

    def _prepare_lug_nuts_path(self):
        ctx = self._ctx
        for i in range(self.lug_nut_count):
            angle = radians(self.LUG_NUTS_INITIAL_ANGLE + i * 360.0 / self.lug_nut_count)
            nut_x = self.bolt_circle_radius * cos(angle)
            nut_y = self.bolt_circle_radius * sin(angle)
            ctx.new_sub_path()
            ctx.arc(nut_x, nut_y, self.lug_nut_radius, 0, radians(360))

    def _prepare_spoke_path(self, start_angle):
        ctx = self._ctx
        inner_r = self.hub_radius
        outer_r = self.rim_radius - self.rim_width
        start_angle = radians(start_angle)
        central_angle = radians(self.spoke_central_angle)
        start_angle -= central_angle / 2.0
        x = cos(start_angle) * outer_r
        y = sin(start_angle) * outer_r

        ctx.arc(0, 0, outer_r, start_angle, start_angle + central_angle)
        ctx.arc_negative(0, 0, inner_r, start_angle + central_angle, start_angle)
        ctx.close_path()

    def _draw_spoke(self, start_angle):
        self._prepare_spoke_path(start_angle)
        # self._ctx.set_line_width(0.1)
        # self._ctx.stroke()
        self._ctx.fill()

    def _draw_spokes(self):
        self._set_color_for_part(self.SPOKES)
        for i in range(self.spoke_count):
            self._draw_spoke(self.SPOKES_INITIAL_ANGLE + i * 360.0 / self.spoke_count)
        self._set_color()

    def _draw_rim(self):
        self._set_color_for_part(self.RIM)
        self._draw_ring(self.rim_radius, self.rim_width)
        self._set_color()

    def _draw_hub_and_lug_nuts(self):
        draw_nuts_as_hub_holes = self.DRAW_NUTS_AS_HUB_HOLES
        if self.HUB in self._err_parts or self.LUG_NUTS in self._err_parts:
            draw_nuts_as_hub_holes = False

        ctx = self._ctx
        if draw_nuts_as_hub_holes:
            # [Preferred method] Prepare paths for outer and inner hub circles and lug nut circles.
            # Then just fill it all and magic happens.
            self._prepare_ring_path(self.hub_radius, self.hub_width)
            self._prepare_lug_nuts_path()
            ctx.set_fill_rule(FillRule.EVEN_ODD)
            ctx.fill()
            # Revert fill rule to default
            ctx.set_fill_rule(FillRule.WINDING)
        else:
            # [Less preferred method] Draw the hub as a ring, then draw the lug nuts over it as solid white circles
            self._set_color_for_part(self.HUB)
            self._draw_ring(self.hub_radius, self.hub_width)
            self._prepare_lug_nuts_path()
            self._set_color_for_part(self.LUG_NUTS)
            ctx.fill()
            # Revert source color to default
            self._set_color()

    def to_dict(self):
        return {
            "scene_length": self._scene_length,
            "x_pixels_per_inch": round(self._x_pixels_per_inch, 3),
            "y_pixels_per_inch": round(self._y_pixels_per_inch, 3),
            "scene_rim_margin": self.SCENE_RIM_MARGIN,
            "lug_nuts_initial_angle": self.LUG_NUTS_INITIAL_ANGLE,
            "spokes_initial_angle": self.SPOKES_INITIAL_ANGLE,
        }

    def generate_svg(self, svg_fpath=None, png=None, color_errors=False):
        """
        Generate SVG representation of the wheel template, and optionally return PNG output.
        @param svg_fpath: path of output SVG file, or None
        @param png: Format of output PNG.
                    None - no PNG output. 
                    "pil" - PIL image. 
                    "bytes" - Raw PNG bytes
                    <file_path> - Save as PNG file instead of returning it
        @param color_errors: Whether to color wheel components that had geometric errors
        """
        self._err_parts = []
        if color_errors:
            _error_strs, self._err_parts = self.check_errors_in_geometry()

        svg_surface = SVGSurface(svg_fpath, self._canvas_w, self._canvas_h)
        ctx = Context(svg_surface)
        self._ctx = ctx

        # First, transform the coordinate system to be centered at 0 and use inches.
        # (-w/2,-w/2) -- (0,-w/2) -- (w/2,-w/2)
        #     |             |            |
        #     |             |            |
        #     |             |            |
        #     |             |            |
        #     |             |            |
        # (-w/2,0) ----- (0, 0) ---- (w/2, 0)
        #     |             |            |
        #     |             |            |
        #     |             |            |
        #     |             |            |
        #     |             |            |
        # (-w/2,w/2) --- (0,w/2) --- (w/2,w/2)
        #
        # where w is the scene width (and height), in inches.
        ctx.scale(self._x_pixels_per_inch, self._y_pixels_per_inch)
        ctx.translate(self._scene_length / 2, self._scene_length / 2)

        self._draw_rim()
        self._draw_hub_and_lug_nuts()
        self._draw_spokes()

        # Create the output PNG if requested
        if not png:
            return

        bio = BytesIO()
        svg_surface.write_to_png(bio)
        if png == "bytes" or png is bytes:
            return bio.getvalue()
        elif png.upper() == "PIL":
            bio.seek(0)
            return Image.open(bio)
        elif png and isinstance(png, str):
            dirpath = os.path.dirname(png)
            if not dirpath or os.path.isdir(dirpath):
                open(png, "wb").write(bio.getvalue())


def produce_wheel_outputs(wt, svg_path, png_path, json_path):
    assert isinstance(wt, WheelTemplate), "'wt' must be instance of WheelTemplate'"
    wt.validate_geometry()
    renderer = WheelTemplateRenderer(wt)
    renderer.generate_svg(svg_path, png=png_path)
    cfg = {
        "specs": wt.to_dict(),
        "image": renderer.to_dict(),
        "geometry": wt.calc_areas()
    }
    open(json_path, "w").write(json.dumps(cfg, indent=4))
    return cfg


def load_wheel_template_from_json(cfg_data):
    try:
        if isinstance(cfg_data, bytes):
            cfg_data = cfg_data.decode()
        cfg = json.loads(cfg_data)
    except Exception as e:
        raise Exception("Error parsing as JSON data: %s" % str(e)) from None

    return WheelTemplate(**cfg["specs"])


def load_wheel_template_from_json_file(fpath):
    return load_wheel_template_from_json(open(fpath, "r"))


if __name__ == "__main__":
    import matplotlib.pyplot as plt
    from matplotlib.image import imread

    kwargs = {}
    if len(sys.argv) > 1:
        cfg = json.load(open(sys.argv[1], "r"))
        kwargs = cfg["specs"]
    wt = WheelTemplate(**kwargs)
    cfg = produce_wheel_outputs(wt, "test_wheel.svg", "test_wheel.png", "test_wheel.json")
    print("Coverage: %.1f%%" % cfg["geometry"]["coverage"])
    plt.imshow(imread("test_wheel.png"))
    plt.show()
