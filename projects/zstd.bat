call "C:\Program Files (x86)\Microsoft Visual Studio\2019\Professional\VC\Auxiliary\Build\vcvars64.bat"

msbuild ../build/VS2010/zstd.sln /p:Configuration=Release /p:Platform=x64


set MY_INSTALL=%INSTALL_PATH%
set "MY_INSTALL=%MY_INSTALL:/=\%"

copy ..\lib\zstd.h %MY_INSTALL%\include\
copy ..\lib\zdict.h %MY_INSTALL%\include\
copy ..\lib\zstd_errors.h %MY_INSTALL%\include\
copy ..\build\VS2010\bin\x64_Release\libzstd.lib %MY_INSTALL%\lib\
copy ..\build\VS2010\bin\x64_Release\libzstd.dll %MY_INSTALL%\bin\
