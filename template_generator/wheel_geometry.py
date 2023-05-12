# importing pycairo
import cairo
import cairosvg
import matplotlib.pyplot as plt
import math
import os
from PIL import Image
from io import BytesIO


class WheelTemplate(object):
    def __init__(self, rim_outer_diameter=20, rim_width=3, hub_outer_diameter=10, hub_width=3,
                 lug_nuts_distance_from_center=4, lug_nuts_diameter=1, number_of_lug_nuts=5,
                 number_of_spokes=5, spoke_width=10, required_coverage_area=0.5, canvas_size=(512, 512)):
        """

        @param rim_outer_diameter: float, inch ["]
        @param rim_width: float, inch ["]
        @param hub_outer_diameter: float, inch ["]
        @param hub_width: float, inch ["]
        @param lug_nuts_distance_from_center: float, inch ["]
        @param lug_nuts_diameter: float, inch ["]
        @param number_of_lug_nuts: int
        @param number_of_spokes: int
        @param spoke_width: float, Degrees (pie slice width)
        @param required_coverage_area: float, solid area out of the total wheel area
        @param canvas_size: set (x-size, y-size) in pixels
        """
        # TODO: check that the given parameters make sense, that we have enough room for everything
        self.rim_outer_diameter = rim_outer_diameter  # inch ["]
        self.rim_width = rim_width  # inch ["]
        self.hub_outer_diameter = hub_outer_diameter  # inch ["]
        self.hub_width = hub_width  # inch ["]
        self.lug_nuts_distance_from_center = lug_nuts_distance_from_center  # inch ["]
        self.lug_nuts_diameter = lug_nuts_diameter  # inch ["]
        self.number_of_lug_nuts = number_of_lug_nuts
        self.number_of_spokes = number_of_spokes  # Divided evenly around the wheel
        self.spoke_width = spoke_width  # Degrees (pie slice width)
        self.required_coverage_area = required_coverage_area  # solid area out of the total wheel area
        self.canvas_size = canvas_size  # in pixels
        self.center_x = self.canvas_size[0]/2  # in pixels
        self.center_y = self.canvas_size[1]/2  # in pixels
        self.x_resolution_scale_factor = self.canvas_size[0] / self.rim_outer_diameter * 1.1  # Pixels for inch
        self.y_resolution_scale_factor = self.canvas_size[1] / self.rim_outer_diameter * 1.1  # Pixels for inch
        self.line_width = 0.04  # default value

    @staticmethod
    def deg2rad(deg):
        return deg*(math.pi/180)

    def generate(self, path_to_svg_file):
        with cairo.SVGSurface(path_to_svg_file, self.canvas_size[0], self.canvas_size[1]) as svg_surface:
            svg_context = cairo.Context(svg_surface)
            svg_context.set_line_width(self.line_width)
            # draw rim
            outer_rim_radius = self.rim_outer_diameter / 2
            inner_rim_radius = outer_rim_radius - self.rim_width
            svg_context.arc(self.center_x, self.center_y, outer_rim_radius, 0, self.deg2rad(360))
            svg_context.arc(self.center_x, self.center_y, inner_rim_radius, 0, self.deg2rad(360))
            # draw hub
            outer_hub_radius = self.hub_outer_diameter / 2
            inner_hub_radius = outer_hub_radius - self.hub_width
            svg_context.arc(self.center_x, self.center_y, outer_hub_radius, 0, self.deg2rad(360))
            svg_context.arc(self.center_x, self.center_y, inner_hub_radius, 0, self.deg2rad(360))












# creating a SVG surface
with cairo.SVGSurface("geek.svg", 700, 700) as surface:
    # creating a cairo context object
    context = cairo.Context(surface)

    # creating a rectangle(square) for left eye
    context.rectangle(100, 100, 100, 100)
    rad = 360 * (math.pi / 180)
    context.arc(50, 50, 100, 0, rad)
    context.set_source_rgba(1, 1, 0, 1)
    # creating a rectangle(square) for right eye
    context.rectangle(500, 100, 100, 100)

    # creating position for the curves
    x, y, x1, y1 = 0.1, 0.5, 0.4, 0.9
    x2, y2, x3, y3 = 0.4, 0.1, 0.9, 0.6

    # setting scale of the context
    context.scale(700, 700)

    # setting line width of the context
    context.set_line_width(0.04)

    # move the context to x,y position
    context.move_to(x, y)

    # draw the curve for smile
    context.curve_to(x1, y1, x2, y2, x3, y3)

    # setting color of the context
    context.set_source_rgba(0.4, 1, 0.4, 1)

    # stroke out the color and width property
    context.stroke()

# printing message when file is saved
print("File Saved")

# Plot svg
img_png = cairosvg.svg2png("... the content of the svg file ...")
img = Image.open(BytesIO(img_png))
plt.imshow(img)
