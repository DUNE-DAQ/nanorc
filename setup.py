from setuptools import setup

# Metadata goes in setup.cfg. These are here for GitHub's dependency graph.
setup(
    name="nanorc",
    install_requires=[
        "click",
        "click-shell",
        "Flask",
        "requests",
        "rich",
        "sh",
        "graphviz",
        "anytree",
        "transitions",
    ],
    extras_require={"develop": [
        "ipdb",
        "ipython"
    ]},
)
