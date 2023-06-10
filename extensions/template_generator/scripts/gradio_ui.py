import re
import os
import time
# from functools import partial
from base64 import b64encode, b64decode
import json
from io import BytesIO

import gradio as gr

try:
    # For standalone mode
    from wheel_geometry import WheelTemplate, WheelTemplateRenderer, produce_wheel_outputs, \
        load_wheel_template_from_json
except ImportError:
    # For 'webui' mode
    from scripts.wheel_geometry import WheelTemplate, WheelTemplateRenderer, produce_wheel_outputs, \
        load_wheel_template_from_json

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

'''

NUM_TEMPLATE_INPUTS = None

DESIGN_ATTR_PARAMS = ["program_project", "model_year", "author", "tags", "vehicle_name_plate", "sub_model"]    
DESIGN_RENDER_PARAMS =  ["prompt",
                      "opts1",
                      "canvas_width", "canvas_height",
                      "batch_size", "creativity", "render_quality"]
                      
NUM_DESIGN_INPUTS = len(DESIGN_ATTR_PARAMS) + len(DESIGN_RENDER_PARAMS)

g_base_dir_path = None
g_output_dir_path = None
g_img_dir_path = None
g_cb_generate_wheel = None


def init_cfg(base_dir_path, output_dir_path, img_dir_path, cb_generate_wheel):
    global g_base_dir_path, g_output_dir_path, g_img_dir_path, g_cb_generate_wheel
    g_base_dir_path = base_dir_path
    g_output_dir_path = output_dir_path
    g_img_dir_path = img_dir_path
    g_cb_generate_wheel = cb_generate_wheel


def gr_create_image_from_file(fpath):
    img_b64 = b64encode(open(fpath, "rb").read()).decode()
    return gr.HTML('<img src="data:image/jpeg;base64,%s" alt="">' % img_b64)


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


def on_generate_wheel_template(live_update, *inputs):
    coverage = gr.Slider.update()
    try:
        wt, err_msg = create_wheel_template_from_ui_inputs(inputs)
        png_image = WheelTemplateRenderer(wt).generate_svg(png="PIL", color_errors=True)
        if not err_msg:
            coverage = wt.calc_areas()["coverage"]
    except Exception as e:
        err_msg = str(e) or str(type(e))
        png_image = gr.Image.update()

    return [png_image, coverage] + make_ui_output_msg(err=err_msg)


def on_generate_wheel_template_live(live_update, *inputs):
    if not live_update:
        return [gr.Image.update(), gr.Slider.update()] + make_ui_no_output_msg()
    return on_generate_wheel_template(live_update, *inputs)


def on_live_update_toggled(live_update, *inputs):
    if live_update:
        # Disable the "Generate" button and generate the output image
        return [gr.Button.update(interactive=False)] + on_generate_wheel_template(live_update, *inputs)
    else:
        # Enable the "Generate" button and don't change any output
        return [gr.Button.update(interactive=True), gr.Image.update(), gr.Slider.update()] + make_ui_no_output_msg()


def on_save_wheel_template(live_update, *inputs):
    try:
        wt, geo_err_msg = create_wheel_template_from_ui_inputs(inputs)
        if geo_err_msg:
            raise Exception(geo_err_msg)
    except Exception as e:
        return make_ui_output_msg(err="Error with template: %s" % str(e))

    try:
        # Separate date/time dir for each execution
        dirname = time.strftime("%Y_%m_%d_%H_%M_%S")
        dirpath = os.path.join(g_output_dir_path, "templates", dirname)
        os.makedirs(dirpath)
        png_fpath = os.path.join(dirpath, "wheel.png")
        svg_fpath = os.path.join(dirpath, "wheel.svg")
        json_fpath = os.path.join(dirpath, "wheel.json")
        produce_wheel_outputs(wt, svg_fpath, png_fpath, json_fpath)
    except Exception as e:
        return make_ui_output_msg(err="Error producing outputs: %s" % str(e))

    return make_ui_output_msg(success="Outputs saved in '%s'" % os.path.relpath(dirpath, g_base_dir_path))

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

def on_load_wheel_template(filedata):
    try:
        wt = load_wheel_template_from_json(filedata)
        outputs = _wheel_template_to_ui_value_list(wt)
    except Exception as e:
        return [gr.update() for i in range(NUM_TEMPLATE_INPUTS + 2)] + make_ui_output_msg(
            err="Error loading wheel template: %s" % str(e))

    return outputs + on_generate_wheel_template(False, *outputs)


def on_generate_designed_wheel(*inputs):
    # print(len(inputs), inputs)
    template_inputs = inputs[:NUM_TEMPLATE_INPUTS]
    design_inputs = inputs[NUM_TEMPLATE_INPUTS:]
    try:
        wt, geo_err_msg = create_wheel_template_from_ui_inputs(template_inputs)
        if geo_err_msg:
            raise Exception(geo_err_msg)
    except Exception as e:
        return [gr.update()] + make_ui_output_msg(err="Error with template: %s" % str(e))

    if g_cb_generate_wheel is None:
        return [gr.update() for i in range(3)]

    DESIGN_INPUT_NAMES = DESIGN_ATTR_PARAMS + DESIGN_RENDER_PARAMS
    try:
        design_input_dict = {DESIGN_INPUT_NAMES[i]: value for i, value in enumerate(design_inputs)}
        designed_image = g_cb_generate_wheel(wt, design_input_dict)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return [gr.update()] + make_ui_output_msg(err="Error with image renderer: %s" % str(e))

    return [designed_image] + make_ui_output_msg(success="Cool!")
    
    
def on_save_designed_wheel(designed_image, *inputs):
    template_inputs = inputs[:NUM_TEMPLATE_INPUTS]
    design_inputs = inputs[NUM_TEMPLATE_INPUTS:]
    try:
        wt, geo_err_msg = create_wheel_template_from_ui_inputs(template_inputs)
        if geo_err_msg:
            raise Exception(geo_err_msg)
    except Exception as e:
        return [gr.update()] + make_ui_output_msg(err="Error with template: %s" % str(e))
                                 
    try:
        attr_dict = {DESIGN_ATTR_PARAMS[i]: value for i, value in enumerate(design_inputs[:len(DESIGN_ATTR_PARAMS)])}
        render_dict = {DESIGN_RENDER_PARAMS[i]: value for i, value in enumerate(design_inputs[len(DESIGN_ATTR_PARAMS):])}
        # Separate date/time dir for each execution
        dirname = time.strftime("%Y_%m_%d_%H_%M_%S")
        dirpath = os.path.join(g_output_dir_path, "designs", dirname)
        os.makedirs(dirpath)
        t_png_fpath = os.path.join(dirpath, "template.png")
        t_svg_fpath = os.path.join(dirpath, "template.svg")
        t_json_fpath = os.path.join(dirpath, "template.json")
        template_cfg = produce_wheel_outputs(wt, t_svg_fpath, t_png_fpath, t_json_fpath)
        
        d_png_fpath = os.path.join(dirpath, "design.png")
        d_json_fpath = os.path.join(dirpath, "design.json")
        png_raw = None
        png_raw_b64 = None
        if designed_image is not None:
            bio = BytesIO()
            designed_image.save(bio, format="png")
            png_raw = bio.getvalue()
            png_raw_b64 = b64encode(png_raw).decode()
        full_cfg = {
            "template": template_cfg,
            "design": {
                "attr": attr_dict,
                "render": render_dict,
                "png_raw_b64": png_raw_b64
            },
        }
        open(d_json_fpath, "w").write(json.dumps(full_cfg, indent=4))
        if png_raw:
            open(d_png_fpath, "wb").write(png_raw)
        
    except Exception as e:
        return make_ui_output_msg(err="Error producing outputs: %s" % str(e))

    return make_ui_output_msg(success="Outputs saved in '%s'" % os.path.relpath(dirpath, g_base_dir_path))

def on_load_designed_wheel(filedata):
    try:
        try:
            if isinstance(filedata, bytes):
                filedata = filedata.decode()
            full_cfg = json.loads(filedata)
        except Exception as e:
            raise Exception("Error parsing as JSON data: %s" % str(e)) from None
        template_cfg = full_cfg["template"]
        design_cfg = full_cfg["design"]
        d_attr_cfg = design_cfg["attr"]
        d_render_cfg = design_cfg["render"]
        png_raw_b64 = design_cfg["png_raw_b64"]
        wt = WheelTemplate(**template_cfg["specs"])
        template_outputs = _wheel_template_to_ui_value_list(wt)
        design_outputs = [d_attr_cfg[k] for k in DESIGN_ATTR_PARAMS]
        design_outputs += [d_render_cfg[k] for k in DESIGN_RENDER_PARAMS]        
        designed_image = None
        if png_raw_b64:
            bio = BytesIO(b64decode(png_raw_b64))
            from PIL import Image
            designed_image = Image.open(bio)
    except Exception as e:
        return [gr.update() for i in range(NUM_TEMPLATE_INPUTS + NUM_DESIGN_INPUTS + 3)] + make_ui_output_msg(
            err="Error loading designed wheel: %s" % str(e))

    return template_outputs + design_outputs + [designed_image] + on_generate_wheel_template(False, *template_outputs)


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
        with gr.Row(variant="compact").style(equal_height=False):
            with gr.Column():
                with gr.Row(variant="compact").style(equal_height=False):
                    with gr.Column():
                        rim_diam = gr.Number(value=wt.rim_diameter, label='Rim diameter ["]',
                                             elem_classes="compact-input")
                        rim_width = gr.Number(value=wt.rim_width, label='Rim width ["]', elem_classes="compact-input")
                        hub_diam = gr.Number(value=wt.hub_diameter, label='Hub diameter ["]',
                                             elem_classes="compact-input")
                        hub_width = gr.Number(value=wt.hub_width, label='Hub width ["]', elem_classes="compact-input")
                        nut_diam = gr.Number(value=wt.lug_nut_diameter, label='Lug nut diameter ["]',
                                             elem_classes="compact-input")
                        bolt_circle_diam = gr.Number(value=wt.bolt_circle_diameter, label='Bolt circle diameter ["]',
                                                     elem_classes="compact-input")

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
                    template_image = gr.Image(initial_template_image, interactive=False)
                    template_image.style(width=400, height=400)
                with gr.Row(variant="compact").style(equal_height=False):
                    load_template_btn = gr.UploadButton("Load template", file_types=[".json"], file_count="single",
                                                        type="bytes")
                    save_template_btn = gr.Button("Save template")

                output_err_textbox = gr.Textbox(show_label=False, visible=False, interactive=False,
                                                elem_classes="error-textbox")
                output_ok_textbox = gr.Textbox(show_label=False, visible=False, interactive=False,
                                               elem_classes="success-textbox")

            with gr.Column():
                with gr.Row(variant="compact").style(equal_height=False):
                    with gr.Column():
                        prog_proj = gr.Textbox(value="", label='Program/Project', elem_classes="compact-input")
                        model_year = gr.Textbox(value="", label='Model Year', elem_classes="compact-input")
                        author = gr.Textbox(value="", label='Author', elem_classes="compact-input")
                        tags = gr.Textbox(value="", label='Tags', elem_classes="compact-input")
                    with gr.Column():
                        name_plate = gr.Textbox(value="", label='Vehicle Name Plate', elem_classes="compact-input")
                        sub_model = gr.Textbox(value="", label='Sub-Model', elem_classes="compact-input")
                prompt = gr.Textbox(value="", lines=3, label='Prompt', placeholder='Prompt')
                with gr.Row(variant="compact").style(equal_height=False):
                    with gr.Column():
                        opts1 = gr.CheckboxGroup(["BEV", "Alloy", "Machining"], label="", info="")
                        opts2 = gr.CheckboxGroup(["reserved1", "reserved2", "reserved3"], label="", info="")
                        canvas_width = gr.Number(value=wt.canvas_size[0], label='Output image width',
                                                 elem_classes="compact-input")
                        canvas_height = gr.Number(value=wt.canvas_size[1], label='Output image height',
                                                  elem_classes="compact-input")
                        batch_size = gr.Slider(1, 50, step=1, value=20, label='Batch Size')
                        creativity = gr.Slider(1, 100, step=1, value=20, label='Creativity')
                        render_quality = gr.Slider(1, 100, step=1, value=20, label='Render quality (takes more time)')
                        reserved_slider = gr.Slider(1, 100, step=1, value=20, label='Reserved slider')
                    with gr.Column():
                        # logo_image = gr.Image(os.path.join(g_img_dir_path, "ford_logo.jpg"), interactive=False)
                        logo_image = gr_create_image_from_file(os.path.join(g_img_dir_path, "wheel_power_logo.jpg"))
                        with gr.Row(variant="compact", elem_classes="image-buttons"):
                            design_generate_btn = gr.Button("Generate", variant="primary")
                            load_design_btn = gr.UploadButton("Load", file_types=[".json"], file_count="single",
                                                                type="bytes")
                            save_design_btn = gr.Button("Save")
                        designed_image = gr.Image(type="pil", interactive=True)
                        designed_image.style(width=350, height=350)

        template_inputs = [
            live_update_switch,
            rim_diam, rim_width,
            hub_diam, hub_width,
            nut_count, nut_diam, bolt_circle_diam,
            spoke_count, spoke_angle,
            req_coverage_area, canvas_width, canvas_height
        ]
        NUM_TEMPLATE_INPUTS = len(template_inputs) - 1 # Omit the live_update_switch

        output_msgs = [output_err_textbox, output_ok_textbox]
        all_outputs = [template_image, real_coverage_area] + output_msgs
        live_update_switch.select(fn=on_live_update_toggled,
                                  inputs=template_inputs,
                                  outputs=[make_template_btn] + all_outputs)
        make_template_btn.click(fn=on_generate_wheel_template, inputs=template_inputs, outputs=all_outputs)
        save_template_btn.click(fn=on_save_wheel_template, inputs=template_inputs, outputs=output_msgs)
        load_template_btn.upload(on_load_wheel_template, inputs=load_template_btn,
                                 outputs=template_inputs[1:] + [template_image, real_coverage_area] + output_msgs)

        # For live updates we need to register event handlers for changes of any input
        for inp in template_inputs:
            if inp is live_update_switch or inp is req_coverage_area:
                # we don't need to watch these
                continue
            inp.change(fn=on_generate_wheel_template_live, inputs=template_inputs, outputs=all_outputs)

            # For designed image generation
        design_inputs = [
            prog_proj, model_year, author, tags, name_plate, sub_model,
            prompt,
            opts1,
            canvas_width, canvas_height,
            batch_size, creativity, render_quality
        ]
        assert NUM_DESIGN_INPUTS == len(design_inputs)
        
        full_inputs = template_inputs[1:] + design_inputs

        design_generate_btn.click(fn=on_generate_designed_wheel, inputs=full_inputs,
                                  outputs=[designed_image] + output_msgs)
        save_design_btn.click(fn=on_save_designed_wheel, inputs=[designed_image] + full_inputs, outputs=output_msgs)
        load_design_btn.upload(fn=on_load_designed_wheel, inputs=load_design_btn, 
                            outputs=full_inputs + [designed_image, template_image, real_coverage_area] + output_msgs)
        
                                  

        return ui


if __name__ == "__main__":
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    OUTPUT_BASE_DIR = os.path.join(BASE_DIR, "generated_wheels")
    IMG_DIR = os.path.join(BASE_DIR, "..", "images")
    init_cfg(BASE_DIR, OUTPUT_BASE_DIR, IMG_DIR, None)
    init_gradio_ui_v1(standalone=True).launch()
    # init_gradio_ui_v2().launch()