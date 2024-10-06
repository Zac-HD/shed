from pathlib import Path

import setuptools

with open("src/shed/__init__.py") as o:
    for line in o:
        if line.startswith("__version__ = "):
            _, __version__, _ = line.split('"')

setuptools.setup(
    name="shed",
    version=__version__,
    author="Zac Hatfield-Dodds",
    author_email="zac@zhd.dev",
    packages=setuptools.find_packages("src"),
    package_dir={"": "src"},
    package_data={"": ["py.typed"]},
    url="https://github.com/Zac-HD/shed",
    project_urls={
        "Source": "https://github.com/Zac-HD/shed/",
        "Changelog": "https://github.com/Zac-HD/shed/blob/master/CHANGELOG.md",
    },
    license="AGPL-3.0",
    description="`shed` canonicalises Python code.",
    install_requires=[
        "black >= 24.1.0",
        "com2ann >= 0.3.0",
        "libcst >= 1.1.0",
        "pyupgrade >= 3.15.0",
        "ruff",
    ],
    python_requires=">=3.9",
    classifiers=[
        "Development Status :: 4 - Beta",
        "License :: OSI Approved :: GNU Affero General Public License v3",
        "Programming Language :: Python :: 3 :: Only",
    ],
    long_description=Path("README.md").read_text(),
    long_description_content_type="text/markdown",
    entry_points={"console_scripts": ["shed=shed._cli:cli"]},
)
