import os

from modules import script_callbacks
# import modules.scripts as scripts
from modules.paths import data_path

import server

def on_ui_tabs():
    ui = server.init_gradio_ui()
    return [(ui, "Wheel Power", "ford_template_generator_tab")]

server.set_dirs(data_path, os.path.join(data_path, "generated_wheels"))
script_callbacks.on_ui_tabs(on_ui_tabs)