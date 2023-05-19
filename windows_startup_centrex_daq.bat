@REM put this file in C:\Users\$USERNAME$\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup to automatically start CeNTREX DAQ on reboot
call activate centrex-daq
python C:\Users\CeNTREX\Documents\GitHub\CeNTREX\main.py --settings C:\Users\CeNTREX\Documents\GitHub\CeNTREX\config\settings_spa_microwaves.ini -start -clear
PAUSE