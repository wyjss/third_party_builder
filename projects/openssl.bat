@echo off
set MY_OPENSSL_EXE=%CACHE_URL%
set "MY_OPENSSL_EXE=%MY_OPENSSL_EXE:/=\%"

set MY_INSTALL=%INSTALL_PATH%
set "MY_INSTALL=%MY_INSTALL:/=\%"


set MY_OPENSSL_ROOT="C:\Program Files\OpenSSL-Win64"
:: 尝试运行 openssl version 命令
if exist %MY_OPENSSL_ROOT%\bin\openssl.exe (
    echo nothing to do
) else (
	echo you need to install openssl... 
    start /wait %MY_OPENSSL_EXE%
)

echo "do not install"
::xcopy %MY_OPENSSL_EXE%\include\openssl %MY_INSTALL%\include\openssl /E /I /H /Y
::copy %MY_OPENSSL_EXE%\lib\VC\x64\MT\libcrypto.lib %MY_INSTALL%\lib
::copy %MY_OPENSSL_EXE%\lib\VC\x64\MT\libssl.lib %MY_INSTALL%\lib
::copy %MY_OPENSSL_EXE%\bin\libssl-3-x64.dll %MY_INSTALL%\bin
::copy %MY_OPENSSL_EXE%\bin\libcrypto-3-x64.dll %MY_INSTALL%\bin
::copy %MY_OPENSSL_EXE%\bin\legacy.dll %MY_INSTALL%\bin