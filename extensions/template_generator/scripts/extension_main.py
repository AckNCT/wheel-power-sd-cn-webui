import os
import importlib
from functools import partial

from modules import script_callbacks
from modules.paths import data_path
from modules.scripts import basedir

from scripts import gradio_ui, wheel_geometry

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
    
def on_generate_final_wheel():
    pass

gradio_ui.init_cfg(data_path, 
                   os.path.join(data_path, "generated_wheel_templates"), 
                   os.path.join(basedir(), "images"),
                   on_generate_final_wheel)
script_callbacks.on_ui_tabs(on_ui_tabs)