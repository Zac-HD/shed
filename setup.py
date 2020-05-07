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
    project_urls={"Funding": "https://github.com/sponsors/Zac-HD"},
    license="AGPL-3.0",
    description="`shed` canonicalises Python code.",
    install_requires=[
        "autoflake >= 1.3.1",
        "black >= 19.10b0",
        "isort >= 4.3.21",
        "pyupgrade >= 2.2.1",
    ],
    python_requires=">=3.6",
    classifiers=[
        "Development Status :: 2 - Pre-Alpha",
        "License :: OSI Approved :: GNU Affero General Public License v3",
        "Programming Language :: Python :: 3 :: Only",
    ],
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    entry_points={"console_scripts": ["shed=shed:cli"]},
)
