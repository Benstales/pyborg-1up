from setuptools import setup, find_packages


def get_long_description():
    with open("README.md") as f:
        long_description = f.read()
    return long_description


setup(
    name="pyborg-custom",
    version="1.0.1",
    python_requires=">=3.7",
    description="Pyborg custom",
    long_description=get_long_description(),
    long_description_content_type="text/markdown",
    packages=find_packages(exclude=['test']),
    include_package_data=True,
    author="Pyborg Team - (Customization: Benstales)",
    url="https://github.com/Benstales/pyborg-1up",
    license="MIT",
    entry_points={
        'console_scripts': ['pyborg_custom=pyborg.pyborg_entrypoint_custom:cli_base'],
    }
)
