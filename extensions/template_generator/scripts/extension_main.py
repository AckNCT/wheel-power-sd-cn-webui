import os
import importlib
from functools import partial
import json
import requests
import io
import base64
from PIL import Image
import PIL.ImageOps

from modules import script_callbacks
from modules.paths import data_path
from modules.scripts import basedir

from scripts import gradio_ui, wheel_geometry, image_utils, controlnet_extracts
# import gradio_ui, wheel_geometry
# Must reload all our internal modules when the WebUI reloads, and in reverse dependency order!

image_utils = importlib.reload(image_utils)
controlnet_extracts = importlib.reload(controlnet_extracts)
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


def on_generate_designed_wheel(template_wheel_img, design_inputs):    
    print(json.dumps(design_inputs, indent=1))
    
    # Basic render params
    prompt = design_inputs.get("prompt", "No entry sign")
    opts1 = list(map(str.lower, design_inputs.get("opts1", [])))
    opts2 = list(map(str.lower, design_inputs.get("opts2", [])))
    height = design_inputs.get("canvas_width", 256)
    width = design_inputs.get("canvas_height", 256)
    batch_size = design_inputs.get("batch_size")
    creativity = design_inputs.get("creativity")
    
    sampler_index = design_inputs.get("sampler_index", 0)
    steps = design_inputs.get("steps", 20)
    
    # Advanced render params
    neg_prompt = design_inputs.get("prompt", "No entry sign")    
    
    # Advanced ControlNet render params
    cn_enabled = design_inputs.get("cn_enabled", True)
    lowvram = design_inputs.get("lowvram", False)
    pixel_perfect = design_inputs.get("pixel_perfect", False)
    
    module = design_inputs.get("module", None)
    model = design_inputs.get("model", None)    
    weight = design_inputs.get("weight", 1.0)
    guidance_start = design_inputs.get("guidance_start", 0)
    guidance_end = design_inputs.get("guidance_end", 1)
    processor_res = design_inputs.get("processor_res", 512)
    threshold_a = design_inputs.get("threshold_a", 64.0)
    threshold_b = design_inputs.get("threshold_b", 64.0)
        
    if 'invert template color' in opts2:
        template_wheel_img = PIL.ImageOps.invert(template_wheel_img)

    template_wheel_img_raw = image_utils.pil_image_to_png_bytes(template_wheel_img)
    template_wheel_img_b64 = base64.b64encode(template_wheel_img_raw).decode('utf-8')

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
        "negative_prompt": "%s %s" % (neg_prompt, "color, illustration, artistic"),
        "eta": 0,
        "s_churn": 0,
        "s_tmax": 0,
        "s_tmin": 0,
        "s_noise": 1,
        "sampler_index": sampler_index,
        "alwayson_scripts": {
            "controlnet": {
                "args": [
                    {
                        "enabled": cn_enabled,
                        "lowvram": lowvram,
                        "pixel_perfect": pixel_perfect,
                        
                        "module": module,
                        # "model": "control_v11p_sd15_canny [d14c016b]",
                        "model": model,
                        
                        "guidance_start": guidance_start,
                        "guidance_end": guidance_end,
                        "weight": weight,
                        
                        "processor_res": processor_res,
                        "threshold_a": threshold_a,
                        "threshold_b": threshold_b,

                        "control_mode": 0,
                        
                        "input_image": template_wheel_img_b64,                        
                    }
                ]
            }
        }
    }
    
    if "mock" in opts2:
        return test_create_random_images(template_wheel_img, batch_size)        
    
    res = requests.post(url_txt2img, json=simple_txt2img)
    r = res.json()
    images = list()
    for img in r['images']:
        images.append(Image.open(io.BytesIO(base64.b64decode(img.split(",", 1)[0]))))
    # img = r['images'][0]
    # image = Image.open(io.BytesIO(base64.b64decode(img.split(",", 1)[0])))
    return images[:len(images)-1]

def test_create_random_images(template_wheel_img, n=1):
    # print(template_wheel_img)
    from PIL import Image, ImageDraw, ImageFont
    import random
    
    # Define the size of the square image
    image_size = 256
    
    # Create a new image with a white background
    images = []
    template_wheel_img2 = template_wheel_img.resize((image_size, image_size))
    for i in range(n):
        image = Image.new("RGB", (image_size, image_size), "white")
        images.append(image)
        # pixels = image.load()
        
        # # Add random noise to each pixel in the image
        # for i in range(image_size):
            # for j in range(image_size):
                # # Generate random RGB values for each pixel
                # red = random.randint(0, 255)
                # green = random.randint(0, 255)
                # blue = random.randint(0, 255)
                # pixels[i, j] = (red, green, blue)
                
        image.paste(template_wheel_img2, (0, 0, image_size, image_size))
        draw = ImageDraw.Draw(image) 
        font = ImageFont.truetype(os.path.join(BASE_DIR, "ariblk.ttf"), 15)
        from random import choice
        rand_text = "".join([choice("abcdefghijklmnopqrstuvwxyz0123456789") for i in range(15)])
          
        # drawing text size
        draw.text((5, 5), "%d %s" % (i, rand_text), font=font, align="left", fill="red")

    return images



BASE_DIR = basedir()
gradio_ui.init_cfg(data_path,
                   os.path.join(data_path, "outputs", "generated_wheels"),
                   os.path.join(BASE_DIR, "images"),
                   on_generate_designed_wheel)
script_callbacks.on_ui_tabs(on_ui_tabs)
