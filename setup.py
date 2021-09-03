from setuptools import setup

# Metadata goes in setup.cfg. These are here for GitHub's dependency graph.
setup(
    name="nanorc",
    install_requires=[
        "click",
        "click-shell",
        "Flask",
        "rich",
        "sh",
        "graphviz",
        "kubernetes",
        "docker",
        "PySocks"
    ],
    extras_require={"develop": [
        "ipdb",
        "ipython"
    ]},
)
