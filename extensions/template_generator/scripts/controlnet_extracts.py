import os
import sys
import gradio as gr

from modules.scripts import scripts_txt2img

_g_controlnet_modules = {}
def controlnet_get_module(module_name):
    if module_name in _g_controlnet_modules:
        return _g_controlnet_modules[module_name]
        
    module_path = os.path.join("extensions", "sd-webui-controlnet", "scripts", "%s.py" % module_name)
    for module in sys.modules.values():
        mpath = getattr(module, "__file__", None)
        if not mpath:
            continue
        if mpath.endswith(module_path):
            _g_controlnet_modules[module_name] = module
            return module
    
    raise Exception("Couldn't find controlnet module '%s'" % module_name)
    
def controlnet_get_module_attr(module_name, attr):
    return getattr(controlnet_get_module(module_name), attr)
    
def controlnet_get_script():
    for script in scripts_txt2img.scripts:
        if script.__module__.lower() == "controlnet.py":
            return script
            
    raise Exception("Couldn't find controlnet Script obj")
    
def controlnet_refresh_all_models(*inputs):
    global_state = controlnet_get_module("global_state")
    global_state.update_cn_models()

    dd = inputs[0]
    selected = dd if dd in global_state.cn_models else "None"
    return gr.Dropdown.update(value=selected, choices=list(global_state.cn_models.keys()))    
    
def controlnet_build_sliders(module, pp):
    self = controlnet_get_script()
    global_state = controlnet_get_module("global_state")
    cn_processor = controlnet_get_module("processor")
    flag_preprocessor_resolution = cn_processor.flag_preprocessor_resolution
    preprocessor_sliders_config = cn_processor.preprocessor_sliders_config
    model_free_preprocessors = cn_processor.model_free_preprocessors
    
    
    grs = []
    module = global_state.get_module_basename(module)
    if module not in preprocessor_sliders_config:
        grs += [
            gr.update(
                label=flag_preprocessor_resolution,
                value=512,
                minimum=64,
                maximum=2048,
                step=1,
                visible=not pp,
                interactive=not pp,
            ),
            gr.update(visible=False, interactive=False),
            gr.update(visible=False, interactive=False),
            gr.update(visible=True),
        ]
    else:
        for slider_config in preprocessor_sliders_config[module]:
            if isinstance(slider_config, dict):
                visible = True
                if slider_config["name"] == flag_preprocessor_resolution:
                    visible = not pp
                grs.append(
                    gr.update(
                        label=slider_config["name"],
                        value=slider_config["value"],
                        minimum=slider_config["min"],
                        maximum=slider_config["max"],
                        step=slider_config["step"]
                        if "step" in slider_config
                        else 1,
                        visible=visible,
                        interactive=visible,
                    )
                )
            else:
                grs.append(gr.update(visible=False, interactive=False))
        while len(grs) < 3:
            grs.append(gr.update(visible=False, interactive=False))
        grs.append(gr.update(visible=True))
    if module in model_free_preprocessors:
        grs += [
            gr.update(visible=False, value="None"),
            gr.update(visible=False),
        ]
    else:
        grs += [gr.update(visible=True), gr.update(visible=True)]
    return grs
    
def controlnet_filter_selected(k, pp):
    self = controlnet_get_script()
    global_state = controlnet_get_module("global_state")
    cn_processor = controlnet_get_module("processor")

    default_option = cn_processor.preprocessor_filters[k]
    pattern = k.lower()
    preprocessor_list = global_state.ui_preprocessor_keys
    model_list = list(global_state.cn_models.keys())
    if pattern == "all":
        return [
            gr.Dropdown.update(value="none", choices=preprocessor_list),
            gr.Dropdown.update(value="None", choices=model_list),
        ] + build_sliders("none", pp)
    filtered_preprocessor_list = [
        x
        for x in preprocessor_list
        if pattern in x.lower() or x.lower() == "none"
    ]
    if pattern in ["canny", "lineart", "scribble", "mlsd"]:
        filtered_preprocessor_list += [
            x for x in preprocessor_list if "invert" in x.lower()
        ]
    filtered_model_list = [
        x for x in model_list if pattern in x.lower() or x.lower() == "none"
    ]
    if default_option not in filtered_preprocessor_list:
        default_option = filtered_preprocessor_list[0]
    if len(filtered_model_list) == 1:
        default_model = "None"
        filtered_model_list = model_list
    else:
        default_model = filtered_model_list[1]
        for x in filtered_model_list:
            if "11" in x.split("[")[0]:
                default_model = x
                break
    return [
        gr.Dropdown.update(
            value=default_option, choices=filtered_preprocessor_list
        ),
        gr.Dropdown.update(
            value=default_model, choices=filtered_model_list
        ),
    ] + controlnet_build_sliders(default_option, pp)