from setuptools import setup

setup(name='centrex',
        version='0.1',
        description='DAQ and theory calculations for the CENTREX experiment',
        url='https://github.com/js216/CeNTREX',
        author='Jakob Kastelic',
        author_email='jakob.kastelic@yale.edu',
        license='GPL2',
        packages=['centrex'],
        install_requires=['pyvisa','pymodbus','pydaqmx'],
        )
