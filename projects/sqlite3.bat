echo MY_VAR=%INSTALL_PATH%

call "C:\Program Files (x86)\Microsoft Visual Studio\2019\Professional\VC\Auxiliary\Build\vcvars64.bat"

cd ..

IF NOT EXIST "sqlite3.dll" (
	cl -Os -O2 -DSQLITE_ENABLE_FTS4 -DSQLITE_ENABLE_RTREE -DSQLITE_ENABLE_COLUMN_METADATA shell.c sqlite3.c -Fesqlite3.exe
	lib sqlite3.obj
	link -dll sqlite3.obj
）ELSE(

)

set MY_INSTALL=%INSTALL_PATH%
set "MY_INSTALL=%MY_INSTALL:/=\%"
copy sqlite3.h %MY_INSTALL%\include
copy sqlite3.lib %MY_INSTALL%\lib
copy sqlite3.dll %MY_INSTALL%\bin
copy sqlite3.exe %MY_INSTALL%\bin