import launch
import os
import pkg_resources

# Stole this file from the 'sd-webui-controlnet' extension

req_file = os.path.join(os.path.dirname(os.path.realpath(__file__)), "requirements.txt")
import sys
print("*******************", sys.version)

with open(req_file) as file:
    for package in file:
        try:
            package = package.strip()
            if package == "gradio":
                # Skip gradio. It comes with the webui anyway. We keep it only for standalone deployments of template-generator.
                continue
                
            if '==' in package:
                package_name, package_version = package.split('==')
                installed_version = pkg_resources.get_distribution(package_name).version
                if installed_version != package_version:
                    launch.run_pip(f"install {package}", f"ford-template-generator requirement: changing {package_name} version from {installed_version} to {package_version}")
            elif not launch.is_installed(package):
                launch.run_pip(f"install {package}", f"ford-template-generator requirement: {package}")
        except Exception as e:
            print(e)
            print(f'Warning: Failed to install {package}, some preprocessors may not work.')