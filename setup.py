import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="WonderPy",
    version="0.1.0",
    author="Orion Elenzil",
    author_email="orion@makewonder.com",
    description="Python API for working with Wonder Workshop robots",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/playi/WonderPy",
    packages=setuptools.find_packages(),
    package_data={'WonderPy': ['lib/WonderWorkshop/osx/*.dylib']},
    classifiers=(
        "Development Status :: 3 - Alpha",
        "Environment :: Console",
        "Environment :: MacOS X",
        "Framework :: Robot Framework",
        "Intended Audience :: Developers",
        "Intended Audience :: Education",
        "Intended Audience :: End Users/Desktop",
        "Intended Audience :: Science/Research",
        "License :: OSI Approved :: MIT License",
        "Operating System :: MacOS",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ),
    keywords=['robots', 'dash', 'dot', 'cue', 'wonder workshop', 'robotics', 'sketchkit',],
    test_suite='test',
    python_requires='>=3.9',
    install_requires=['svgpathtools', 'PyObjC', 'bleak'],
    # this also requires a Python 3 compatible fork of Adafruit_BluefruitLE.
)
