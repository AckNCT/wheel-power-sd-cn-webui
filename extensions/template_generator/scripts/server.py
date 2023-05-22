import gradio as gr
import re
import os
import time
# import json
# import traceback

from wheel_geometry import WheelTemplate, WheelTemplateRenderer, produce_wheel_outputs

CSS = '''
.error-textbox textarea {
    background-color: #FFCCCB;
}
.success-textbox textarea {
    background-color: #CBFFCC;
}
'''

g_base_dir_path = None
g_output_dir_path = None

def set_dirs(base_dir_path, output_dir_path):
    global g_base_dir_path, g_output_dir_path
    g_base_dir_path = base_dir_path
    g_output_dir_path = output_dir_path
    

def create_wheel_template_from_ui_inputs(inputs):
    [rim_diam, rim_width, hub_diam, hub_width, nut_count, nut_diam, bolt_circle_diam, spoke_count, spoke_angle,
     req_coverage_area, canvas_res_str] = inputs

    try:
        width, height = re.match(r"(\d+)[xX ,.](\d+)", canvas_res_str.strip()).groups()
        canvas_res = int(width), int(height)
        req_coverage_area /= 100
    except:
        raise Exception("Invalid canvas resolution. Must be '<width> <height>'") from None

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


def on_generate_wheel(live_update, *inputs):
    coverage = gr.Slider.update()
    try:
        wt, err_msg = create_wheel_template_from_ui_inputs(inputs)
        png_image = WheelTemplateRenderer(wt).generate_svg(png="PIL", color_errors=True)
        if not err_msg:
            coverage = wt.calc_areas()["coverage"]
    except Exception as e:
        err_msg = str(e) or str(type(e))
        png_image = gr.Image.update()

    return [png_image, coverage, *make_ui_output_msg(err=err_msg)]


def on_generate_wheel_live(live_update, *inputs):
    if not live_update:
        return [gr.Image.update(), gr.Slider.update(), *make_ui_no_output_msg()]
    return on_generate_wheel(live_update, *inputs)


def on_live_update_toggled(live_update, *inputs):
    if live_update:
        # Disable the "Generate" button and generate the output image
        return [gr.Button.update(interactive=False), *on_generate_wheel(live_update, *inputs)]
    else:
        # Enable the "Generate" button and don't change any output
        return [gr.Button.update(interactive=True), gr.Image.update(), gr.Slider.update(), *make_ui_no_output_msg()]


def on_save(live_update, *inputs):
    try:
        wt, geo_err_msg = create_wheel_template_from_ui_inputs(inputs)
        if geo_err_msg:
            raise Exception(geo_err_msg)
    except Exception as e:
        return make_ui_output_msg(err="Error with template: %s" % str(e))

    try:
        # Separate date/time dir for each execution
        dirname = time.strftime("%Y_%m_%d_%H_%M_%S")
        dirpath = os.path.join(g_output_dir_path, dirname)
        os.makedirs(dirpath)
        png_fpath = os.path.join(dirpath, "wheel.png")
        svg_fpath = os.path.join(dirpath, "wheel.svg")
        json_fpath = os.path.join(dirpath, "wheel.json")
        produce_wheel_outputs(wt, svg_fpath, png_fpath, json_fpath)
    except Exception as e:
        return make_ui_output_msg(err="Error producing outputs: %s" % str(e))

    return make_ui_output_msg(success="Outputs saved in %s" % os.path.relpath(dirpath, g_base_dir_path))


def init_gradio_ui(**kwargs):
    with gr.Blocks(css=CSS, **kwargs) as ui:
        with gr.Row():
            with gr.Column():
                with gr.Row():
                    rim_diam = gr.Number(value=17, label='Rim diameter ["]')
                    rim_width = gr.Number(value=1, label='Rim width ["]')

                with gr.Row():
                    hub_diam = gr.Number(value=5, label='Hub diameter ["]')
                    hub_width = gr.Number(value=2, label='Hub width ["]')

                with gr.Row():
                    live_update_switch = gr.Checkbox(value=False, label="Live update")
                    generate_btn = gr.Button("Generate")
                    save_tn = gr.Button("Save")

            with gr.Column():
                with gr.Row():
                    nut_count = gr.Slider(3, 9, step=1, value=5, label='Lug nut count')
                    nut_diam = gr.Number(value=0.8, label='Lug nut diameter ["]')
                    bolt_circle_diam = gr.Number(value=2.5, label='Bolt circle diameter ["]')

                with gr.Row():
                    spoke_count = gr.Slider(3, 9, step=1, value=5, label='Spoke count')
                    spoke_angle = gr.Slider(5, 70, step=1, value=10, label='Spoke central angle')

                with gr.Row():
                    req_coverage_area = gr.Slider(0, 100, value=20, step=1, label='Requested coverage area [%]')
                    real_coverage_area = gr.Slider(0, 100, value=0, step=0.1, interactive=False,
                                                   label='Actual coverage area [%]')
                    canvas_res = gr.Textbox(value="512 512", label='Canvas resolution')

        inputs = [
            live_update_switch,
            rim_diam, rim_width,
            hub_diam, hub_width,
            nut_count, nut_diam, bolt_circle_diam,
            spoke_count, spoke_angle,
            req_coverage_area, canvas_res
        ]

        output_image = gr.Image(interactive=False)
        output_image.style(width=512, height=512)
        output_err_textbox = gr.Textbox(show_label=False, visible=False, interactive=False,
                                        elem_classes="error-textbox")
        output_ok_textbox = gr.Textbox(show_label=False, visible=False, interactive=False,
                                       elem_classes="success-textbox")
        output_msgs = [output_err_textbox, output_ok_textbox]
        all_outputs = [output_image, real_coverage_area, *output_msgs]
        live_update_switch.select(fn=on_live_update_toggled,
                                  inputs=inputs,
                                  outputs=[generate_btn, *all_outputs])
        generate_btn.click(fn=on_generate_wheel, inputs=inputs, outputs=all_outputs)
        save_tn.click(fn=on_save, inputs=inputs, outputs=output_msgs)

        # For live updates we need to register event handlers for changes of any input
        for inp in inputs:
            if inp is live_update_switch or inp is req_coverage_area:
                # we don't need to watch these
                continue
            inp.change(fn=on_generate_wheel_live, inputs=inputs, outputs=all_outputs)

        return ui

if __name__ == "__main__":
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    OUTPUT_BASE_DIR = os.path.join(BASE_DIR, "generated_wheels")
    set_dirs(BASE_DIR, OUTPUT_BASE_DIR)
    init_gradio_ui().launch()
