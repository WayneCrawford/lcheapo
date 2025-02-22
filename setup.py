import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

version = {}
with open("lcheapo/version.py") as fp:
    exec(fp.read(), version)

setuptools.setup(
    name="lcheapo",
    version=version['__version__'],
    author="Wayne Crawford",
    author_email="crawford@ipgp.fr",
    description="LCHEAPO data routines",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/WayneCrawford/lcheapo",
    packages=setuptools.find_packages(),
    include_package_data=True,
    install_requires=[
          'obspy>=1.1',
          'pyyaml>5.0',
          'jsonschema>=2.6',
          'jsonref>=0.2',
          'progress>=1.5',
          'numpy<2.0',
          'sdpchainpy>=1.0b2',
          'tiskitpy>=0.4'
      ],
    entry_points={
         'console_scripts': [
             'lcfix=lcheapo.lcfix:main',
             'lcdump=lcheapo.lcdump:main',
             'lccut=lcheapo.lccut:main',
             'lcinfo=lcheapo.lcinfo:main',
             'lcheader=lcheapo.lcheader:main',
             'lcplot=lcheapo.lcplot:main',
             'lc2SDS_py=lcheapo.lc2SDS:main',
             'lc2ms_py=lcheapo.lc2ms:main',
             'lc_examples=lcheapo.lcputexamples:main'
         ]
    },
    python_requires='>=3.8',
    classifiers=[
        "Development Status :: 4 - Beta",
        "Environment :: Console",
        "Intended Audience :: Science/Research",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: GNU General Public License v3 (GPLv3)",
        "Natural Language :: English",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3.6",
        "Topic :: Scientific/Engineering",
        "Topic :: Scientific/Engineering :: Physics"
    ],
    keywords='oceanography, marine, OBS'
)
