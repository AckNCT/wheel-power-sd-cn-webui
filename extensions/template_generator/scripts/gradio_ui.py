import re
import os
import time
import shutil
# from functools import partial
from base64 import b64encode, b64decode
import json
from io import BytesIO
from zipfile import ZipFile
import sys
from operator import itemgetter

from modules.ui import create_refresh_button, save_style_symbol
from modules.ui_components import ToolButton, FormRow
from modules.scripts import scripts_txt2img
from modules.sd_samplers import samplers as sd_samplers
import gradio as gr

try:
    # For standalone mode
    from wheel_geometry import WheelTemplate, WheelTemplateRenderer, produce_wheel_outputs, \
        save_wheel_json, load_wheel_template_from_json
    from image_utils import image_file_as_png_bytes, pil_image_to_png_bytes
except ImportError:
    # For 'webui' mode
    from scripts.wheel_geometry import WheelTemplate, WheelTemplateRenderer, produce_wheel_outputs, \
        save_wheel_json, load_wheel_template_from_json
    from scripts.image_utils import image_file_as_png_bytes, pil_image_to_png_bytes

g_controlnet_modules = {}
def get_controlnet_module(module_name):
    if module_name in g_controlnet_modules:
        return g_controlnet_modules[module_name]
        
    module_path = os.path.join("extensions", "sd-webui-controlnet", "scripts", "%s.py" % module_name)
    for module in sys.modules.values():
        mpath = getattr(module, "__file__", None)
        if not mpath:
            continue
        if mpath.endswith(module_path):
            g_controlnet_modules[module_name] = module
            return module
    
    raise Exception("Couldn't find controlnet module '%s'" % module_name)
    
def get_controlnet_script():
    for script in scripts_txt2img.scripts:
        if script.__module__.lower() == "controlnet.py":
            return script
            
    raise Exception("Couldn't find controlnet Script obj")
    
def controlnet_refresh_all_models(*inputs):
    global_state = get_controlnet_module("global_state")
    global_state.update_cn_models()

    dd = inputs[0]
    selected = dd if dd in global_state.cn_models else "None"
    return gr.Dropdown.update(value=selected, choices=list(global_state.cn_models.keys()))    
    
def controlnet_build_sliders(module, pp):
    self = get_controlnet_script()
    cn_processor = get_controlnet_module("processor")
    flag_preprocessor_resolution = cn_processor.flag_preprocessor_resolution
    preprocessor_sliders_config = cn_processor.preprocessor_sliders_config
    model_free_preprocessors = cn_processor.model_free_preprocessors
    
    
    grs = []
    module = self.get_module_basename(module)
    if module not in preprocessor_sliders_config:
        grs += [
            gr.update(label=flag_preprocessor_resolution, value=512, minimum=64, maximum=2048, step=1, visible=not pp, interactive=not pp),
            gr.update(visible=False, interactive=False),
            gr.update(visible=False, interactive=False),
            gr.update(visible=True)
        ]
    else:
        for slider_config in preprocessor_sliders_config[module]:
            if isinstance(slider_config, dict):
                visible = True
                if slider_config['name'] == flag_preprocessor_resolution:
                    visible = not pp
                grs.append(gr.update(
                    label=slider_config['name'],
                    value=slider_config['value'],
                    minimum=slider_config['min'],
                    maximum=slider_config['max'],
                    step=slider_config['step'] if 'step' in slider_config else 1,
                    visible=visible,
                    interactive=visible))
            else:
                grs.append(gr.update(visible=False, interactive=False))
        while len(grs) < 3:
            grs.append(gr.update(visible=False, interactive=False))
        grs.append(gr.update(visible=True))
    if module in model_free_preprocessors:
        grs += [gr.update(visible=False, value='None'), gr.update(visible=False)]
    else:
        grs += [gr.update(visible=True), gr.update(visible=True)]
    return grs
    

CSS = '''
.error-textbox textarea {
    background-color: #FFCCCB;
}
.success-textbox textarea {
    background-color: black;
}
.compact-input input {
    width: 100px !important;
    float: right;
    padding: 5px !important;
}
.compact-input textarea {
    width: 200px !important;
    float: right;
    padding: 5px !important;
    height: 32px;
}
.compact-file {
    min-width: 30px !important;
}
'''

NUM_TEMPLATE_INPUTS = None

DESIGN_ATTR_PARAMS = [
    "program_project", "model_year", "author", "tags", "name_plate", "sub_model"
]
DESIGN_BASE_RENDER_PARAMS = [
    "prompt",
    "opts1", "opts2", "canvas_width", "canvas_height",
    "batch_size", "creativity", "sampler_index", "steps",
]

DESIGN_ADV_RENDER_PARAMS = [
    "neg_prompt"
]
DESIGN_ADV_CONTROLNET_RENDER_PARAMS = [
    "cn_enabled", "lowvram", "pixel_perfect",
    "module", "model",
    "weight", "guidance_start", "guidance_end",
    "processor_res", "threshold_a", "threshold_b",
]
DESIGN_RENDER_PARAMS = DESIGN_BASE_RENDER_PARAMS + DESIGN_ADV_RENDER_PARAMS + DESIGN_ADV_CONTROLNET_RENDER_PARAMS

DESIGN_INPUT_NAMES = DESIGN_ATTR_PARAMS + DESIGN_RENDER_PARAMS                        
NUM_DESIGN_INPUTS = len(DESIGN_INPUT_NAMES)

g_base_dir_path = None # Base dir of this extension
g_output_dir_path = None # Base dir for all outputs stored on server (Doesn't have to be inside g_base_dir_path)
g_img_dir_path = None # Dir for static images (e.g. Ford logo)
g_cb_generate_wheel = None # Callback to invoke on generation of final designed wheel

TEMPLATES_DIR_NAME = "templates" # Dir under g_output_dir_path to save wheel templates
DESIGNS_DIR_NAME = "designs" # Dir under g_output_dir_path to save final designed wheels
WHEEL_JSON = "wheel.json" # Name of JSON file containing wheel template configuration

REFRESH_SYMBOL = '\U0001f504'  # 🔄
# SAVE_STYLE_SYMBOL = '\U0001f4be'  # 💾
SAVE_STYLE_SYMBOL = '\U0001f4be'


def init_cfg(base_dir_path, output_dir_path, img_dir_path, cb_generate_wheel):
    global g_base_dir_path, g_output_dir_path, g_img_dir_path, g_cb_generate_wheel
    g_base_dir_path = base_dir_path
    g_output_dir_path = output_dir_path
    g_img_dir_path = img_dir_path
    g_cb_generate_wheel = cb_generate_wheel

def gr_hide():
    return gr.update(visible=False)
    
def gr_show():
    return gr.update(visible=True)

def gr_create_image_from_file(fpath):
    img_b64 = b64encode(open(fpath, "rb").read()).decode()
    return gr.HTML('<img src="data:image/jpeg;base64,%s" alt="">' % img_b64)
    
def gr_create_local_file_href_html(fpath):    
    fname = "%s_%s" % (os.path.basename(os.path.dirname(fpath)), os.path.basename(fpath))
    return '<a href="/file=%s" target="_blank" download="%s">%s</a>' % (fpath, fname, SAVE_STYLE_SYMBOL)

def create_wheel_template_from_ui_inputs(inputs):
    if len(inputs) == 11:
        # V1
        raise NotImplementedError("Obsolete, move to init_gradio_ui_v2")

        # (rim_diam, rim_width, hub_diam, hub_width, nut_count, nut_diam, bolt_circle_diam, spoke_count, spoke_angle,
        # req_coverage_area, canvas_res_str) = inputs

        # try:
        # width, height = re.match(r"(\d+)[xX ,.](\d+)", canvas_res_str.strip()).groups()
        # canvas_res = int(width), int(height)
        # except:
        # raise Exception("Invalid canvas resolution. Must be '<width> <height>'") from None
    elif len(inputs) == NUM_TEMPLATE_INPUTS:
        # V2
        (rim_diam, rim_width, hub_diam, hub_width, nut_count, nut_diam, bolt_circle_diam, spoke_count, spoke_angle,
         req_coverage_area, canvas_width, canvas_height) = inputs
        canvas_res = (canvas_width, canvas_height)

    req_coverage_area /= 100
    wt = WheelTemplate(rim_diam, rim_width, hub_diam, hub_width, nut_count, nut_diam, bolt_circle_diam,
                       spoke_count, spoke_angle, req_coverage_area, canvas_res)
    try:
        wt.validate_geometry()
        geo_err_str = ""
    except Exception as e:
        geo_err_str = str(e)
    return wt, geo_err_str


def make_ui_output_msg(err=None, success=None):
    assert not (err and success), "Cannot pass both 'err' and 'success'"
    err_output = gr.Textbox.update(value=err, visible=True) if err else gr.Textbox.update(value="", visible=False)
    ok_output = gr.Textbox.update(value=success, visible=True) if success else gr.Textbox.update(value="",
                                                                                                 visible=False)
    return [err_output, ok_output]


def make_ui_no_output_msg():
    return [gr.Textbox.update(), gr.Textbox.update()]


def on_generate_wheel_template(user_state, live_update, *inputs):
    coverage = gr.Slider.update()
    try:
        wt, err_msg = create_wheel_template_from_ui_inputs(inputs)
        png_image = WheelTemplateRenderer(wt).generate_svg(png="PIL", color_errors=True)
        if not err_msg:
            coverage = wt.calc_areas()["coverage"]
    except Exception as e:
        err_msg = str(e) or str(type(e))
        png_image = gr.Image.update()

    user_state["custom_template"] = False
    return [user_state, png_image, coverage] + make_ui_output_msg(err=err_msg)


def on_generate_wheel_template_live(user_state, live_update, *inputs):
    if not live_update or user_state.get("custom_template", False):
        return [user_state, gr.Image.update(), gr.Slider.update()] + make_ui_no_output_msg()
    return on_generate_wheel_template(user_state, live_update, *inputs)


def on_live_update_toggled(user_state, live_update, *inputs):
    if live_update:
        # Disable the "Generate" button and generate the output image
        return [gr.Button.update(interactive=False)] + on_generate_wheel_template(user_state, live_update, *inputs)
    else:
        # Enable the "Generate" button and don't change any output
        return [gr.Button.update(interactive=True), gr.update(), gr.Image.update(), gr.Slider.update()] + make_ui_no_output_msg()

    
def get_server_saved_template_dirs(max_recent=15):
    dir_path = os.path.join(g_output_dir_path, TEMPLATES_DIR_NAME)
    fnames = os.listdir(dir_path)
    res = []
    mtimes = {}
    for fname in fnames:
        fpath = os.path.join(dir_path, fname)
        if not os.path.isdir(fpath):
            continue
        if not os.path.isfile(os.path.join(fpath, WHEEL_JSON)):
            continue
        res.append(fname)
        mtimes[fname] = os.stat(fpath).st_mtime
    res.sort(key=lambda fname:mtimes[fname], reverse=True)
    return res[:max_recent]

def on_save_wheel_template(live_update, *inputs):
    try:
        wt, geo_err_msg = create_wheel_template_from_ui_inputs(inputs[:len(inputs)-1])
        if geo_err_msg:
            raise Exception(geo_err_msg)
    except Exception as e:
        return [gr.update()] + make_ui_output_msg(err="Error with template: %s" % str(e))

    try:
        # Separate date/time dir for each execution
        dirname = "%s_%s" % ('_'.join(inputs[-1].split()), time.strftime("%Y_%m_%d_%H_%M_%S"))
        dirpath = os.path.join(g_output_dir_path, "templates", dirname)
        os.makedirs(dirpath)
        png_fpath = os.path.join(dirpath, "wheel.png")
        svg_fpath = os.path.join(dirpath, "wheel.svg")
        json_fpath = os.path.join(dirpath, WHEEL_JSON)
        produce_wheel_outputs(wt, svg_fpath, png_fpath, json_fpath)
    except Exception as e:
        return [gr.update()] + make_ui_output_msg(err="Error producing outputs: %s" % str(e))

    return [gr.Dropdown.update(choices=get_server_saved_template_dirs())] + \
        make_ui_output_msg(success="Outputs saved in '%s'" % os.path.relpath(dirpath, g_base_dir_path))

def _wheel_template_to_ui_value_list(wt):
    assert isinstance(wt, WheelTemplate)
    rim_diam = wt.rim_diameter
    rim_width = wt.rim_width
    hub_diam = wt.hub_diameter
    hub_width = wt.hub_width
    nut_count = wt.lug_nut_count
    nut_diam = wt.lug_nut_diameter
    bolt_circle_diam = wt.bolt_circle_diameter
    spoke_count = wt.spoke_count
    spoke_angle = wt.spoke_central_angle
    req_coverage_area = wt.required_coverage_area * 100  # Expected here in %
    canvas_width = wt.canvas_size[0]
    canvas_height = wt.canvas_size[1]

    outputs = [rim_diam, rim_width, hub_diam, hub_width, nut_count, nut_diam, bolt_circle_diam, spoke_count,
               spoke_angle,
               req_coverage_area, canvas_width, canvas_height]

    return outputs


def on_load_wheel_template_from_dropdown(user_state, selected_template_folder):
    """
    Load from a chosen file saved on the server
    """
    try:
        template_json_filename = os.path.join(g_output_dir_path, TEMPLATES_DIR_NAME, selected_template_folder, WHEEL_JSON)
        with open(template_json_filename, 'rb') as template_json_handler:
            filedata = template_json_handler.read()
        wt = load_wheel_template_from_json(filedata)
        outputs = _wheel_template_to_ui_value_list(wt)
    except Exception as e:
        return [gr.update() for i in range(NUM_TEMPLATE_INPUTS + 3)] + make_ui_output_msg(
            err="Error loading wheel template: %s" % str(e))
    return outputs + on_generate_wheel_template(user_state, False, *outputs)


def on_load_wheel_template_from_file(user_state, filedata):
    """
    Load from file uploaded by the client
    """
    try:
        wt = load_wheel_template_from_json(filedata)
        outputs = _wheel_template_to_ui_value_list(wt)
    except Exception as e:
        return [gr.update() for i in range(NUM_TEMPLATE_INPUTS + 2)] + make_ui_output_msg(
            err="Error loading wheel template: %s" % str(e))

    return outputs + on_generate_wheel_template(user_state, False, *outputs)


def on_upload_template_image(user_state, template_image):
    user_state["custom_template"] = True
    return [user_state, template_image] + make_ui_output_msg(success="uploaded user template")


def on_generate_designed_wheel(template_image, *inputs):
    # print(len(inputs), inputs)
    design_inputs = inputs
    
    # template_inputs = inputs[:NUM_TEMPLATE_INPUTS]    
    # design_inputs = inputs[NUM_TEMPLATE_INPUTS:]    
    # try:
        # wt, geo_err_msg = create_wheel_template_from_ui_inputs(template_inputs)
        # if geo_err_msg:
            # raise Exception(geo_err_msg)
    # except Exception as e:
        # return [gr.update()] + make_ui_output_msg(err="Error with template: %s" % str(e))

    if g_cb_generate_wheel is None:
        return [gr_hide()] + [gr.update() for i in range(3)]

    try:
        design_input_dict = {DESIGN_INPUT_NAMES[i]: value for i, value in enumerate(design_inputs)}
        # designed_image = g_cb_generate_wheel(wt, design_input_dict)
        designed_images = g_cb_generate_wheel(template_image, design_input_dict)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return [gr_hide(), gr.update()] + make_ui_output_msg(err="Error with image renderer: %s" % str(e))

    return [gr_hide(), designed_images] + make_ui_output_msg(success="Cool!")


def on_save_designed_wheel(template_image, designed_images, *inputs):
    # print(designed_images)
    # return [gr.update()] + make_ui_output_msg(err="sdfg")
    
    template_inputs = inputs[:NUM_TEMPLATE_INPUTS]
    design_inputs = inputs[NUM_TEMPLATE_INPUTS:]
    try:
        wt, geo_err_msg = create_wheel_template_from_ui_inputs(template_inputs)
        if geo_err_msg:
            # raise Exception(geo_err_msg)
            # Save it anyway
            pass
    except Exception as e:
        return [gr_hide] + make_ui_output_msg(err="Error with template: %s" % str(e))

    try:
        attr_dict = {DESIGN_ATTR_PARAMS[i]: value for i, value in enumerate(design_inputs[:len(DESIGN_ATTR_PARAMS)])}
        render_dict = {DESIGN_RENDER_PARAMS[i]: value for i, value in
                       enumerate(design_inputs[len(DESIGN_ATTR_PARAMS):])}
        # Separate date/time dir for each execution
        dirname = time.strftime("%Y_%m_%d_%H_%M_%S")
        dirpath = os.path.join(g_output_dir_path, "designs", dirname)
        os.makedirs(dirpath)
        # t_png_fpath = os.path.join(dirpath, "template.png")
        # t_svg_fpath = os.path.join(dirpath, "template.svg")
        t_json_fpath = os.path.join(dirpath, "template.json")
        save_wheel_json(wt, t_json_fpath)
        # template_cfg = produce_wheel_outputs(wt, t_svg_fpath, t_png_fpath, t_json_fpath)

        template_raw = pil_image_to_png_bytes(template_image)
        template_png_fpath = os.path.join(dirpath, "template.png")
        open(template_png_fpath, "wb").write(template_raw)
        template_raw_b64 = b64encode(template_raw).decode()        

        png_raw_b64_list = []
        d_png_paths = []
        for index, image in enumerate(designed_images):
            d_png_fpath = os.path.join(dirpath, "design_%s.png" % index)
            d_png_paths.append(d_png_fpath)
            tmp_png_fname = image.get('name', None)
            if tmp_png_fname is not None:
                # shutil.copy2(tmp_png_fname, d_png_fpath)
                png_raw = image_file_as_png_bytes(tmp_png_fname)
                open(d_png_fpath, "wb").write(png_raw)
                png_raw_b64 = b64encode(png_raw).decode()
            else:
                png_raw_b64 = None
            png_raw_b64_list.append(png_raw_b64)
        full_cfg = {
            "template_specs": wt.to_dict(),
            "template_raw_b64": template_raw_b64,
            "design": {
                "attr": attr_dict,
                "render": render_dict,
                "png_raw_b64_list": png_raw_b64_list
            },
        }
        d_json_fpath = os.path.join(dirpath, "design.json")
        open(d_json_fpath, "w").write(json.dumps(full_cfg, indent=4))

    except Exception as e:
        return [gr_hide()] + make_ui_output_msg(err="Error producing outputs: %s" % str(e))

    output_zip_fpath = os.path.join(dirpath, "design.zip")
    with ZipFile(output_zip_fpath, 'w') as z:
        z.write(t_json_fpath, os.path.basename(t_json_fpath))
        z.write(template_png_fpath, os.path.basename(template_png_fpath))
        for d_png_fpath in d_png_paths:
            z.write(d_png_fpath, os.path.basename(d_png_fpath))
        z.write(d_json_fpath, os.path.basename(d_json_fpath))
    
    down_btn_update = gr.update(value=gr_create_local_file_href_html(output_zip_fpath), visible=True)
    return [down_btn_update] + make_ui_output_msg(success="Outputs saved in '%s'" % os.path.relpath(dirpath, g_base_dir_path))


def on_load_designed_wheel(user_state, filedata):
    try:
        try:
            if isinstance(filedata, bytes):
                filedata = filedata.decode()
            full_cfg = json.loads(filedata)
        except Exception as e:
            raise Exception("Error parsing as JSON data: %s" % str(e)) from None
        template_specs = full_cfg["template_specs"]
        template_raw64 = full_cfg["template_raw_b64"]
        design_cfg = full_cfg["design"]
        d_attr_cfg = design_cfg["attr"]
        d_render_cfg = design_cfg["render"]
        png_raw_b64_list = design_cfg["png_raw_b64_list"]
        wt = WheelTemplate(**template_specs)
        template_outputs = _wheel_template_to_ui_value_list(wt)
        design_outputs = [d_attr_cfg[k] for k in DESIGN_ATTR_PARAMS]
        design_outputs += [d_render_cfg[k] for k in DESIGN_RENDER_PARAMS]
        designed_images = []
        from PIL import Image
        template_image = Image.open(BytesIO(b64decode(template_raw64)))
        for png_raw_b64 in png_raw_b64_list:
            if png_raw_b64 is None:
                continue
            bio = BytesIO(b64decode(png_raw_b64))
            designed_images.append(Image.open(bio))
            
    except Exception as e:
        return [gr_hide()] + [gr.update() for i in range(NUM_TEMPLATE_INPUTS + NUM_DESIGN_INPUTS + 4)] + make_ui_output_msg(
            err="Error loading designed wheel: %s" % str(e))

    user_state["custom_template"] = True
    return [gr_hide(), user_state] + template_outputs + design_outputs + [template_image, designed_images] + make_ui_output_msg(success="Cool!")


def init_gradio_ui_v1(standalone=False):
    raise NotImplementedError("Obsolete, move to init_gradio_ui_v2")

    # Create a default wheel template for initial UI state
    # TODO: Maybe load it from the most recent saved template
    # wt = WheelTemplate()
    # real_coverage_area = wt.calc_areas()["coverage"]
    # initial_template_image = WheelTemplateRenderer(wt).generate_svg(png="PIL", color_errors=True)

    # with gr.Blocks(css=CSS, analytics_enabled=standalone) as ui:
    # with gr.Row():
    # with gr.Column():
    # with gr.Row():
    # rim_diam = gr.Number(value=wt.rim_diameter, label='Rim diameter ["]')
    # rim_width = gr.Number(value=wt.rim_width, label='Rim width ["]')

    # with gr.Row():
    # hub_diam = gr.Number(value=wt.hub_diameter, label='Hub diameter ["]')
    # hub_width = gr.Number(value=wt.hub_width, label='Hub width ["]')

    # with gr.Row():
    # live_update_switch = gr.Checkbox(value=False, label="Live update")
    # generate_btn = gr.Button("Generate")
    # save_template_btn = gr.Button("Save")

    # with gr.Column():
    # with gr.Row():
    # nut_count = gr.Slider(3, 9, step=1, value=wt.lug_nut_count, label='Lug nut count')
    # nut_diam = gr.Number(value=wt.lug_nut_diameter, label='Lug nut diameter ["]')
    # bolt_circle_diam = gr.Number(value=wt.bolt_circle_diameter, label='Bolt circle diameter ["]')

    # with gr.Row():
    # spoke_count = gr.Slider(3, 9, step=1, value=wt.spoke_count, label='Spoke count')
    # spoke_angle = gr.Slider(5, 70, step=1, value=wt.spoke_central_angle, label='Spoke central angle')

    # with gr.Row():
    # req_coverage_area = gr.Slider(0, 100, value=wt.required_coverage_area * 100, step=1,
    # label='Requested coverage area [%]')
    # real_coverage_area = gr.Slider(0, 100, value=real_coverage_area, step=0.1, interactive=False,
    # label='Actual coverage area [%]')
    # canvas_res = gr.Textbox(value="%d %d" % wt.canvas_size, label='Canvas resolution')

    # inputs = [
    # live_update_switch,
    # rim_diam, rim_width,
    # hub_diam, hub_width,
    # nut_count, nut_diam, bolt_circle_diam,
    # spoke_count, spoke_angle,
    # req_coverage_area, canvas_res
    # ]

    # template_image = gr.Image(initial_template_image, interactive=False)
    # template_image.style(width=512, height=512)
    # output_err_textbox = gr.Textbox(show_label=False, visible=False, interactive=False,
    # elem_classes="error-textbox")
    # output_ok_textbox = gr.Textbox(show_label=False, visible=False, interactive=False,
    # elem_classes="success-textbox")
    # output_msgs = [output_err_textbox, output_ok_textbox]
    # all_outputs = [template_image, real_coverage_area] + output_msgs
    # live_update_switch.select(fn=on_live_update_toggled,
    # inputs=inputs,
    # outputs=[generate_btn] + all_outputs)
    # generate_btn.click(fn=on_generate_wheel_template, inputs=inputs, outputs=all_outputs)
    # save_template_btn.click(fn=on_save_wheel_template, inputs=inputs, outputs=output_msgs)

    # # For live updates we need to register event handlers for changes of any input
    # for inp in inputs:
    # if inp is live_update_switch or inp is req_coverage_area:
    # # we don't need to watch these
    # continue
    # inp.change(fn=on_generate_wheel_template_live, inputs=inputs, outputs=all_outputs)

    # return ui


def init_gradio_ui_v2(standalone=False):
    global NUM_TEMPLATE_INPUTS

    # Create a default wheel template for initial UI state
    # TODO: Maybe load it from the most recent saved template
    wt = WheelTemplate()
    real_coverage_area = wt.calc_areas()["coverage"]
    initial_template_image = WheelTemplateRenderer(wt).generate_svg(png="PIL", color_errors=True)

    with gr.Blocks(css=CSS, analytics_enabled=standalone) as ui:
        user_state = gr.State(value={"test": 1234})
        with gr.Row(variant="compact").style(equal_height=False):
            with gr.Column():
                with gr.Row(variant="compact").style(equal_height=False):
                    with gr.Column():
                        rim_diam = gr.Slider(10, 50, step=1, value=wt.rim_diameter, label='Rim diameter ["]')
                        rim_width = gr.Slider(1, 49, step=1, value=wt.rim_width, label='Rim width ["]')
                        hub_diam = gr.Slider(5, 48, step=1, value=wt.hub_diameter, label='Hub diameter ["]')
                        hub_width = gr.Slider(1, 47, step=1, value=wt.hub_width, label='Hub width ["]')
                        nut_diam = gr.Slider(1, 4, step=0.5, value=wt.lug_nut_diameter, label='Lug nut diameter ["]')
                        bolt_circle_diam = gr.Slider(2, 40, step=1,
                                                     value=wt.bolt_circle_diameter, label='Bolt circle diameter ["]')

                    with gr.Column():
                        spoke_angle = gr.Slider(5, 70, step=1, value=wt.spoke_central_angle,
                                                label='Spoke central angle')
                        spoke_count = gr.Slider(3, 9, step=1, value=wt.spoke_count, label='Spoke count')
                        nut_count = gr.Slider(3, 9, step=1, value=wt.lug_nut_count, label='Lug nut count')
                        req_coverage_area = gr.Slider(0, 100, value=wt.required_coverage_area, step=1,
                                                      label='Requested coverage area [%]', visible=False)
                        real_coverage_area = gr.Slider(0, 100, value=real_coverage_area, step=0.1, interactive=False,
                                                       label='Actual coverage area [%]')
                        with gr.Row(variant="compact").style():
                            live_update_switch = gr.Checkbox(value=False, label="Live preview")
                            make_template_btn = gr.Button("Preview template")

                with gr.Row(variant="compact").style(equal_height=False):
                    template_image = gr.Image(initial_template_image, type="pil", interactive=True)
                    template_image.style(width=400, height=400)
                with gr.Row(variant="compact").style(equal_height=False):
                    # load_template_btn = gr.UploadButton("Load template", file_types=[".json"], file_count="single",
                    #                                     type="bytes")
                    template_name = gr.Textbox(value="", label='Template Name', max_lines=1, show_label=True,
                                               interactive=True)
                    save_template_btn = ToolButton(value=save_style_symbol, elem_id='save_template_button')
                    # save_template_btn = gr.Button("Save template", lable='Save Wheel Template', show_lable=True)
                    saved_templates = gr.Dropdown(label='Load Saved Template', multiselect=False, show_label=True,
                                                  interactive=True, visible=True, choices=get_server_saved_template_dirs(),
                                                  elem_id='saved_templates_dropdown')
                    create_refresh_button(saved_templates, dir,
                                          refreshed_args=lambda: {"choices": get_server_saved_template_dirs()},
                                          elem_id='refresh_saved_templates')

                output_err_textbox = gr.Textbox(show_label=False, visible=False, interactive=False,
                                                elem_classes="error-textbox")
                output_ok_textbox = gr.Textbox(show_label=False, visible=False, interactive=False,
                                               elem_classes="success-textbox")

            with gr.Column():
                with gr.Row(variant="compact").style(equal_height=False):
                    with gr.Column():
                        program_project = gr.Textbox(value="", label='Program/Project', elem_classes="compact-input")
                        model_year = gr.Textbox(value="", label='Model Year', elem_classes="compact-input")
                        author = gr.Textbox(value="", label='Author', elem_classes="compact-input")
                        tags = gr.Textbox(value="", label='Tags', elem_classes="compact-input")
                    with gr.Column():
                        name_plate = gr.Textbox(value="", label='Vehicle Name Plate', elem_classes="compact-input")
                        sub_model = gr.Textbox(value="", label='Sub-Model', elem_classes="compact-input")
                prompt = gr.Textbox(label="Prompt", show_label=False, lines=3, placeholder='Prompt')
                with gr.Row(variant="compact").style(equal_height=False):
                    with gr.Column():
                        opts1 = gr.CheckboxGroup(["BEV", "Alloy", "Machining"], label="", info="")
                        opts2 = gr.CheckboxGroup(["Invert template color", "reserved2", "Mock"], label="", info="")
                        canvas_width = gr.Number(value=wt.canvas_size[0], label='Output image width',
                                                 elem_classes="compact-input", minimum=64, maximum=512)
                        canvas_height = gr.Number(value=wt.canvas_size[1], label='Output image height',
                                                  elem_classes="compact-input", minimum=64, maximum=512)
                        batch_size = gr.Slider(1, 50, step=1, value=1, label='Batch Size')
                        creativity = gr.Slider(1, 30, step=1, value=7, label='Creativity')
                        # steps = gr.Slider(1, 100, step=1, value=20, label='Render quality (takes more time)')
                        with FormRow():
                            sampler_index = gr.Dropdown(label='Sampling method', choices=[x.name for x in sd_samplers], value=sd_samplers[0].name)
                            steps = gr.Slider(minimum=1, maximum=150, step=1, label="Sampling steps", value=20)

                    with gr.Column():
                        # logo_image = gr.Image(os.path.join(g_img_dir_path, "ford_logo.jpg"), interactive=False)
                        logo_image = gr_create_image_from_file(os.path.join(g_img_dir_path, "wheel_power_logo.jpg"))
                        with gr.Row(variant="compact", elem_classes="image-buttons", equal_height=True):
                            design_generate_btn = gr.Button("Generate", variant="primary")
                            load_design_btn = gr.UploadButton("Load", file_types=[".json"], file_count="single",
                                                              type="bytes")
                            save_design_btn = gr.Button("Save")
                            # download_design_btn = gr.File(interactive=False, visible=False, \
                                                        # show_label=False, elem_classes="compact-file")
                            download_design_btn = gr.HTML("<p></p>", elem_classes="lg secondary tool compact-file", visible=False)
                        designed_image = gr.Gallery(show_label=False).style(columns=2)
                        # designed_image = gr.Image(type="pil", interactive=True)
                        designed_image.style(width=350, height=350)
                with gr.Accordion("More txt2img options"):                        
                    neg_prompt = gr.Textbox(label="Negative prompt", show_label=False, lines=3, placeholder="Negative prompt")                        
                with gr.Accordion("More ControlNet options"):
                    with FormRow(elem_classes="checkboxes-row", variant="compact"):
                        cn_enabled = gr.Checkbox(label='Enable', value=True)
                        lowvram = gr.Checkbox(label='Low VRAM', value=False)
                        pixel_perfect = gr.Checkbox(label='Pixel Perfect', value=False)
                        # preprocessor_preview = gr.Checkbox(label='Allow Preview', value=False)
                
                    with gr.Row():
                        global_state = get_controlnet_module("global_state")
                        cn = get_controlnet_script()
                        module = gr.Dropdown(global_state.ui_preprocessor_keys, label=f"Preprocessor", value=None)
                        # trigger_preprocessor = ToolButton(value=trigger_symbol, visible=True, elem_id=f'{elem_id_tabname}_{tabname}_controlnet_trigger_preprocessor')
                        model = gr.Dropdown(list(global_state.cn_models.keys()), label=f"Model", value=None)
                        refresh_models = ToolButton(value=REFRESH_SYMBOL)
                        refresh_models.click(controlnet_refresh_all_models, model, model)
            
                    with gr.Row():
                        weight = gr.Slider(label="Control Weight", value=1.25, minimum=0.0, maximum=2.0, step=.05, interactive=True)
                        guidance_start = gr.Slider(label="Starting Control Step", value=0, minimum=0.0, maximum=1.0, interactive=True)
                        guidance_end = gr.Slider(label="Ending Control Step", value=2, minimum=0.0, maximum=1.0, interactive=True)
                        
                    # advanced options
                    with gr.Column(visible=False) as cn_advanced:
                        processor_res = gr.Slider(label="Preprocessor resolution", value=512, minimum=64, maximum=2048, visible=False, interactive=False)
                        threshold_a = gr.Slider(label="Threshold A", value=64, minimum=64, maximum=1024, visible=False, interactive=False)
                        threshold_b = gr.Slider(label="Threshold B", value=64, minimum=64, maximum=1024, visible=False, interactive=False)
                        
                    module.change(controlnet_build_sliders, inputs=[module, pixel_perfect], outputs=[processor_res, threshold_a, threshold_b, cn_advanced, model, refresh_models])
                    pixel_perfect.change(controlnet_build_sliders, inputs=[module, pixel_perfect], outputs=[processor_res, threshold_a, threshold_b, cn_advanced, model, refresh_models])
                        
                        
                

        template_inputs = [
            live_update_switch,
            rim_diam, rim_width,
            hub_diam, hub_width,
            nut_count, nut_diam, bolt_circle_diam,
            spoke_count, spoke_angle,
            req_coverage_area, canvas_width, canvas_height
        ]
        NUM_TEMPLATE_INPUTS = len(template_inputs) - 1  # Omit the live_update_switch

        output_msgs = [output_err_textbox, output_ok_textbox]
        all_outputs = [template_image, real_coverage_area] + output_msgs
        live_update_switch.select(fn=on_live_update_toggled,
                                  inputs=[user_state] + template_inputs,
                                  outputs=[make_template_btn, user_state] + all_outputs)
        make_template_btn.click(fn=on_generate_wheel_template, inputs=[user_state] + template_inputs, 
                                outputs=[user_state] + all_outputs)
        save_template_btn.click(fn=on_save_wheel_template, inputs=template_inputs + [template_name],
                                outputs=[saved_templates] + output_msgs)
        # load_template_btn.upload(on_load_wheel_template_from_file, inputs=load_template_btn,
        #                          outputs=template_inputs[1:] + [user_state, template_image, real_coverage_area] + output_msgs)
        saved_templates.change(fn=on_load_wheel_template_from_dropdown, inputs=[user_state, saved_templates],
                               outputs=template_inputs[1:] + [user_state, template_image, real_coverage_area] + output_msgs)
        template_image.upload(fn=on_upload_template_image, inputs=[user_state, template_image],
                              outputs=[user_state, template_image]
                              + output_msgs)

        # For live updates we need to register event handlers for changes of any input
        for inp in template_inputs:
            if inp is live_update_switch or inp is req_coverage_area:
                # we don't need to watch these
                continue
            inp.change(fn=on_generate_wheel_template_live, inputs=[user_state] + template_inputs, 
                        outputs=[user_state] + all_outputs)

        # For designed image generation
        design_inputs = list(itemgetter(*DESIGN_INPUT_NAMES)(locals()))
        full_inputs = template_inputs[1:] + design_inputs

        design_generate_btn.click(fn=on_generate_designed_wheel, inputs=[template_image] + design_inputs,
                                  outputs=[download_design_btn, designed_image] + output_msgs)
        save_design_btn.click(fn=on_save_designed_wheel, inputs=[template_image, designed_image] + full_inputs, 
                                outputs=[download_design_btn] + output_msgs)
        load_design_btn.upload(fn=on_load_designed_wheel, inputs=[user_state, load_design_btn],
                               outputs=[download_design_btn, user_state] + full_inputs + [template_image, designed_image] + output_msgs)

        return ui


if __name__ == "__main__":
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    OUTPUT_BASE_DIR = os.path.join(BASE_DIR, "generated_wheels")
    IMG_DIR = os.path.join(BASE_DIR, "..", "images")
    init_cfg(BASE_DIR, OUTPUT_BASE_DIR, IMG_DIR, None)
    init_gradio_ui_v1(standalone=True).launch()
    # init_gradio_ui_v2().launch()
