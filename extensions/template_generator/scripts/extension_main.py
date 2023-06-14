import os
import importlib
from functools import partial
import json
import requests
import io
import base64
from PIL import Image

from modules import script_callbacks
from modules.paths import data_path
from modules.scripts import basedir

# from scripts import gradio_ui, wheel_geometry
import gradio_ui, wheel_geometry
# Must reload all our internal modules when the WebUI reloads, and in reverse dependency order!

wheel_geometry = importlib.reload(wheel_geometry)
gradio_ui = importlib.reload(gradio_ui)


def _gradio_blocks_render_patch_use_child_css(self):
    # This patches the root gradio block to include our custom CSS, otherwise only the root block's custom css is used 
    # for all the document
    from gradio.context import Context
    from gradio.blocks import Blocks
    if self.css:
        root_block = Context.root_block
        if root_block is not None:
            if root_block.css:
                # Append if the root has one
                root_block.css += "\r\n" + self.css
            else:
                root_block.css = self.css

    return Blocks.render(self)


def on_ui_tabs():
    ui = gradio_ui.init_gradio_ui_v2()
    # Do the ugly patch
    ui.render = partial(_gradio_blocks_render_patch_use_child_css, ui)
    return [(ui, "Wheel Power", "ford_template_generator_tab")]


def on_generate_designed_wheel(wt, design_inputs):
    print(json.dumps(design_inputs, indent=1))
    design_inputs.get("prog_proj")
    design_inputs.get("model_year")
    design_inputs.get("author")
    design_inputs.get("tags")
    design_inputs.get("name_plate")
    design_inputs.get("sub_model")
    prompt = design_inputs.get("prompt", "No entry sign")
    design_inputs.get("opts1")
    design_inputs.get("opts2")
    height = design_inputs.get("canvas_width", 256)
    width = design_inputs.get("canvas_height", 256)
    batch_size = design_inputs.get("batch_size")
    creativity = design_inputs.get("creativity")
    steps = design_inputs.get("render_quality", 20)
    guidance = design_inputs.get("guidance")

    png_image = wheel_geometry.WheelTemplateRenderer(wt).generate_svg(png="bytes", color_errors=True)
    encoded_image = base64.b64encode(png_image).decode('utf-8')

    url_txt2img = "http://localhost:7860/sdapi/v1/txt2img"
    simple_txt2img = {
        "enable_hr": False,
        "denoising_strength": 0,
        "firstphase_width": 0,
        "firstphase_height": 0,
        "prompt": "%s %s" % (prompt, "alloy wheel design, automotive design, performance, suv, electric car wheel, "
                                     "19”, 22”, velar, front view, dark background, clean image, automotive "
                                     "photography, 50mm"),
        "styles": [],
        "seed": -1,
        "subseed": -1,
        "subseed_strength": 0,
        "seed_resize_from_h": -1,
        "seed_resize_from_w": -1,
        "batch_size": batch_size,
        "n_iter": 1,
        "steps": steps,
        "cfg_scale": creativity,
        "width": width,
        "height": height,
        "restore_faces": False,
        "tiling": False,
        "negative_prompt": "color, illustration, artistic",
        "eta": 0,
        "s_churn": 0,
        "s_tmax": 0,
        "s_tmin": 0,
        "s_noise": 1,
        "sampler_index": "Euler a",
        "alwayson_scripts": {
            "controlnet": {
                "args": [
                    {
                        "input_image": encoded_image,
                        "module": "canny",
                        "model": "control_v11p_sd15_canny [d14c016b]",
                        "guidance": guidance,
                        "weight": 1.25,
                        "threshold_a": 100,
                        "threshold_b": 200,
                    }
                ]
            }
        }
    }
    res = requests.post(url_txt2img, json=simple_txt2img)
    r = res.json()
    img = r['images'][0]
    image = Image.open(io.BytesIO(base64.b64decode(img.split(",", 1)[0])))
    # ====== sample ======

    # from PIL import Image
    # import random
    #
    # # Define the size of the square image
    # image_size = 256
    #
    # # Create a new image with a white background
    # image = Image.new("RGB", (image_size, image_size), "white")
    # pixels = image.load()
    #
    # # Add random noise to each pixel in the image
    # for i in range(image_size):
    #     for j in range(image_size):
    #         # Generate random RGB values for each pixel
    #         red = random.randint(0, 255)
    #         green = random.randint(0, 255)
    #         blue = random.randint(0, 255)
    #         pixels[i, j] = (red, green, blue)

    # ====== end of sample ======

    return image


gradio_ui.init_cfg(data_path,
                   os.path.join(data_path, "outputs", "generated_wheels"),
                   os.path.join(basedir(), "images"),
                   on_generate_designed_wheel)
script_callbacks.on_ui_tabs(on_ui_tabs)
