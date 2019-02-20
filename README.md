# Yaesu_CAT_python
python module for Yaesu radio operation, including FT-450/891/991/2000/DX Series

demo (already in device.py `demo` function):

```
import device
a = device.RIG_CREATOR()        # 创建设备工厂类, 准备设备配置
a.show_ports()                  # 打印所有可用串口

rig = a.get('FT-891')           # 使用工厂类创建指定型号设备

rig.connect('/dev/ttyUSB0', 38400)  # 连接USB串口上连接的设备
if not rig.connect_status():
    print 'Connect fail.'
    return

# 可以这样调用某种功能, 所有可用功能请查阅 YEASU_CAT3.yaml
rig.func_exec('VFO_A_GET')               # GET
rig.func_exec('VFO_A_GET', debug=True)   # GET的调试功能, 会认为设备返回[DEBUG]中的数据, 然后解析返回, 测试用
rig.func_exec('AF_GAIN_SET', VAL=10)     # SET, 参数名称参考配置文件, 如YEASU_CAT3.yaml

```