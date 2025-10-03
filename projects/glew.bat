set MY_INSTALL=%INSTALL_PATH%
set "MY_INSTALL=%MY_INSTALL:/=\%"

cd ..
xcopy .\include\GL\ %MY_INSTALL%\include\GL /E /I /H /Y
copy .\lib\Release\x64\glew32.lib %MY_INSTALL%\lib
copy .\lib\Release\x64\glew32s.lib %MY_INSTALL%\lib
copy .\bin\Release\x64\glew32.dll %MY_INSTALL%\bin
copy .\bin\Release\x64\glewinfo.exe %MY_INSTALL%\bin
copy .\bin\Release\x64\visualinfo.exe %MY_INSTALL%\bin