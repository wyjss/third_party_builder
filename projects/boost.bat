cd ..
call "C:\Program Files (x86)\Microsoft Visual Studio\2019\Professional\VC\Auxiliary\Build\vcvars64.bat"
call bootstrap.bat

set MY_INSTALL=%INSTALL_PATH%
set "MY_INSTALL=%MY_INSTALL:/=\%"

b2.exe --prefix=%MY_INSTALL%  toolset=msvc-16.0 address-model=64 --build-dir=%BUILD_PATH% link=static variant=release threading=multi runtime-link=static install
