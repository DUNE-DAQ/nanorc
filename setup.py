from setuptools import setup

# Metadata goes in setup.cfg. These are here for GitHub's dependency graph.
setup(
    name="nanorc",
    package_data={
        'nanorc': [
            ## yes, I really hate this too
            'webuidata/*',
            'webuidata/*/*',
            'webuidata/*/*/*',
            'webuidata/*/*/*/*',
            'webuidata/*/*/*/*/*',
            'webuidata/*/*/*/*/*/*',
            'webuidata/*/*/*/*/*/*/*',
            'webuidata/*/*/*/*/*/*/*/*',
            'confdata/*']
    },
    install_requires=[
        "click",
        "click-shell",
        "Flask",
        "Flask-HTTPAuth",
        "Flask-RESTful",
        "Flask-Cors",
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
