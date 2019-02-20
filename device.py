#!/usr/bin/env python
# -*- coding: utf-8 -*-
# 
# 本模块包含操作设备(电台, SDR, GPS, RTC等)的类
# 1. CAT指令执行过程产生的报错, 由调用方识别并处理, CAT相关类中完成错误的返回.
# 2. 

import os
import re
import sys
import yaml
import time
import copy
import logging
import serial
import serial.tools.list_ports

class Logger(logging.Logger):
    # 日志记录类, 输出日志到控制台和日志文件
    # DEBUG - INFO - WARNING - ERROR - CRITICAL
    # 为缩小日志文件, 日志文件记录INFO及以上; 控制台输出WARNING及以上
    def __init__(self, filename='main.log'):
        super(Logger, self).__init__(self)
        
        if not os.path.exists(filename):
            f = open(filename, 'w')
            f.close()

        fh = logging.FileHandler(filename)
        fh.setLevel(logging.DEBUG)

        ch = logging.StreamHandler() 
        ch.setLevel(logging.INFO) 

        formatter_simple = logging.Formatter('[%(asctime)s][%(levelname)s]: %(message)s') 
        # formatter = logging.Formatter('[%(asctime)s]%(filename)s<%(funcName)s:%(lineno)d>[%(levelname)s]: %(message)s') 
        fh.setFormatter(formatter_simple) 
        ch.setFormatter(formatter_simple) 

        self.addHandler(fh) 
        self.addHandler(ch)

class RIG_CREATOR(object):
    # 设备工厂类, 用来配置并产生指定型号的类实例. 此类中不要求连接设备,
    # 只提供命令配置检查和传入, 设备连接在rig.connect中完成.
    def __init__(self):
        ''' 初始化设备配置列表 '''
        with open('conf/support_model.yaml','r') as f:
            self.__config_dict = yaml.load(f)['RADIO_CONF']
        self.logger = Logger()

    def auto_match(self):
        # 查找tty/ttyUSB, 尝试以不同速率连接.
        # TODO: 1. 完成yeasu_cat3协议的自动匹配
        #       2. 支持更多品牌和协议
        model = ''
        for baudrate in (4800, 9600, 19200, 38400):
            for p in serial.tools.list_ports.comports():
                auto_rig = serial.Serial(p.device, baudrate)

        return self.get(model)

    # def get_ports(self):
    #     ''' 获取系统所有可用串口 '''
    #     port_list = list(serial.tools.list_ports.comports())
    #     # 返回 serial.tools.list_ports.ListPortInfo 对象迭代器
    #     # 更详细信息: https://pythonhosted.org/pyserial/tools.html
    #     if port_list == []:
    #         self.logger.warning('No available serial port.')
    #         return
    #     return port_list
        
    def show_ports(self):
        ''' 打印所有串口信息, 功能等同: $python -m serial.tools.list_ports '''
        for p in serial.tools.list_ports.comports():
            print 'dev: %s - %s - %s\nhwid: %s' % (
                p.device, p.product, p.manufacturer, p.hwid)
            print '-------------------------'

    def get(self, model):
        ''' 创建相应型号的类实例 '''
        try:
            assert self.__config_dict.has_key(model), 'can\'t find [%s] in file \'conf/support_model.yaml\' - [RADIO_CONF]' % model
            radio_confs = self.__config_dict[model]['CONF']
            radio_class = self.__config_dict[model]['CLASS']
            
            # 合并配置列表, 依次加载通用配置和个性化配置
            config = self.merge_conf(radio_confs)   
            assert config is not None, 'config interrupt or incomplete.'
            assert self.check_conf(config), 'config check failed.'
        except AssertionError, e:
            self.logger.error(e)
        except Exception, e:
            self.logger.error(e)
        else:
            self.logger.info('%s created, %d funcs.' % (model, len(config)))
            return eval(radio_class)(model, config)
        
    def merge_conf(self, conf_list):
        '''
        调用 dict.update 将多个配置文件覆盖方式的合并.
        请注意update的特点, 若value为字典, 不会递归update, 修改配置请将单个功能
        全部拷贝到新文件修改. 否则将导致配置不完整, 然后添加到配置文件列表中
        '''
        merged = {}
        for path in conf_list:
            self.logger.info('load config: [%s]' % path)
            try:
                with open(path,'r') as f:
                    conf = yaml.load(f)
                    assert conf is not None, 'empty config.'
                    merged.update(conf)
            except Exception, e:
                self.logger.error(e)
                return

        if merged <> {}:
            return merged
        else:
            self.logger.error('no valid config.')
            return

    def check_conf(self, conf):
        '''
        检查配置文件是否符合以下规则: 
        1. 每个功能配置, 必须有非空的CMD
        2. _GET命令, 若RET不为空, 需符合以下三者之一:
            - 若为维度类, 需在DIM中有对应参数
            - 若为数值类, 需在CONVERT中有对应参数
            - 或原值返回
        3. _SET命令, CMD中若有参数变量, 需符合以下二者之一:
            - 若为维度类, 需在DIM中有对应参数
            - 若为数值类, 需在CONVERT中有对应参数
        4. 特殊情况: IF_SHIFT_GET 两者都有

        配置文件检查前置, 节省执行中检查时间
        TODO: 1. 是统一输出, 还是现场报错
        '''
        try:
            for func_name, func_conf in conf.iteritems():
                # self.logger.debug('check func: [%s]' % func_name)
                # ERR 0X: 函数名称检查
                assert func_name.endswith('_GET') or func_name.endswith('_SET'), '[%s] ERR 01: not _GET or _SET type.' % func_name
                assert func_conf is not None, '[%s] ERR 02: empty config.' % func_name

                # ERR 1X: CMD 检查
                assert func_conf.get('CMD') is not None, '[%s] ERR 11: no [CMD] part.' % func_name
                assert isinstance(func_conf.get('CMD'), str), '[%s] ERR 12: [CMD] not a str' % func_name
                assert func_conf.get('CMD').endswith(';'), '[%s] ERR 13: missing ; in [CMD] end.' % func_name

                if func_name.endswith('_GET'):
                    assert func_conf.get('RET') is not None, '[%s] ERR 21: _GET - RET empty or None.' % func_name
                    assert func_conf.get('DEBUG') is not None, '[%s] ERR 26: _GET - DEBUG empty or None.' % func_name
                    
                    # DIM 或 CONVERT 不可同时为空, 考虑是否需要为直接返回原始值设计(允许同时为空或设计特殊符号).
                    # assert func_conf.get('DIM') is not None or func_conf.get('CONVERT') is not None, '[%s] ERR 22: _GET - DIM and CONVERT both None.' % func_name
                    
                    # 检查 RET 下的每个元素
                    for ret_name, ret_conf in func_conf.get('RET').iteritems():    
                        assert re.match(r'\d+,\d+', ret_conf), '[%s] ERR 23: _GET - RET interception syntax error' % func_name
                        assert eval(ret_conf)[0] < eval(ret_conf)[1], '[%s] ERR 24: _GET - RET interception position error, begin > end' % func_name

                        var_pass = False
                        if func_conf.get('DIM') is not None and func_conf.get('DIM').get(ret_name) is not None:
                            var_pass = True
                        if func_conf.get('CONVERT') is not None and func_conf.get('CONVERT').get(ret_name) is not None:
                            var_pass = True
                        
                        # 此条考虑放开, 因某些情况下, RET需要原样返回, 非DIM或CONVERT
                        # 或CONVERT中包含'原样返回'功能
                        # assert var_pass, '[%s] ERR 25: _GET - RET can not find corresponding config in DIM or CONVERT' % func_name

                elif func_name.endswith('_SET'):
                    params = re.finditer(r'\{\$\w+\}', func_conf.get('CMD'))
                    if params:
                        # 检查CMD中每个参数变量
                        for pa in params:
                            var = pa.group()[2:-1]
                            var_pass = False
                            if func_conf.get('DIM') is not None and func_conf.get('DIM').get(var) is not None:
                                var_pass = True
                            if func_conf.get('CONVERT') is not None and func_conf.get('CONVERT').get(var) is not None:
                                var_pass = True
                            assert var_pass, '[%s] ERR 31: _SET - can not find vars in [DIM] or [CONVERT]' % func_name

        except Exception, e:
            self.logger.error('func config [%s] fail.' % func_name)
            self.logger.warning(e)
            return False
        else:
            return True

class YAESU_CAT(object):
    def __init__(self, model, config):
        self.model = model
        self.__func_dict = config
        self.__conn = serial.Serial()
        self.logger = Logger()
        self.logger.info('----- INIT: %s -----' % model)

    def __del__(self):
        self.logger.info('quit.')
        if self.__conn.is_open:
            self.__conn.close()
    
    def get_func(self):
        return copy.deepcopy(self.__func_dict)
    
    def get_model(self):
        return self.func_exec('ID_GET')

    def connect_status(self):
        ''' 返回连接状态 '''
        return self.__conn.is_open

    def connect_auto(self):
        # 尝试以不同速率连接所有串口, 尝试获取ID
        # TODO: 1. 支持更多品牌和协议 
        model_id = ''
        for baudrate in (4800, 9600, 19200, 38400):
            for p in serial.tools.list_ports.comports():
                self.__conn = serial.Serial(p.device, baudrate)
                model_id = self.get_model()
                if model_id:
                    return model_id
        return

    def connect(
        self 
        ,port='/dev/ttyUSB0'
        ,baudrate=38400
        ,bytesize=serial.EIGHTBITS
        ,parity=serial.PARITY_NONE
        ,stopbits=serial.STOPBITS_ONE
        ,timeout=0          # 读超时
        ,write_timeout=1    # 写超时
        ):
        ''' 连接设备, open串口, 成功/失败返回True/False 
        timeout: read()超时, None=等待直到返回, 0=无阻塞模式
        '''

        if self.__conn.is_open:
            self.logger.debug('already connected: %s@%s' % (port, baudrate))
            return True
        
        if self.__conn.port:
            # 若串口已经初始化, 则重新打开, 不重复初始化
            try:
                self.__conn.open()
            except IOError, e:      # serial.SerialException
                self.logger.error('serial open failed.')
                return False
            else:
                self.logger.info('serial open successful.')
                return True
        else:
            try:
                assert baudrate in (4800, 9600, 19200, 38400), 'unsupported baudrate.'
                self.__conn.port          = port
                self.__conn.baudrate      = baudrate
                self.__conn.bytesize      = bytesize
                self.__conn.parity        = parity
                self.__conn.stopbits      = stopbits
                self.__conn.write_timeout = write_timeout
                self.__conn.timeout       = timeout
                self.__conn.open()
            except serial.SerialException, e:
                self.logger.error('serial error: %s@%s' % (port, baudrate))
                self.logger.error(e)
                return False
            except Exception,e:
                self.logger.error(e)  
                return False
            else:
                self.logger.debug('serial connected: %s@%s' % (port, baudrate))
                return True

    def cmd_rw_test(self, command):
        ''' 发送命令并查看返回 '''
        self.__conn.reset_input_buffer()
        self.__conn.write(command.encode('utf-8'))
        self.__conn.flush()
        print 'SEND: %s' % command
        
        recv_str = ''
        time.sleep(0.5)
        if self.__conn.in_waiting:
            recv_str = self.__conn.read(self.__conn.in_waiting).decode('utf-8')
            recv_str = recv_str.split(';')[-2]
            print 'RECV: %s' % recv_str
        else:
            print 'NO RECV'

    def cmd_rw(self, command, debug=False, func_name=None, err_flag='?'):
        ''' 
        GET命令, 返回是否执行成功(失败返回None), 可能的异常:
        串口未开启, 读取超时, 读到设备返回的指定错误码, 过程中发生异常
        '''
        # 是否DEBUG模式, 返回GET配置中的DEBUG数据
        if debug:
            assert func_name is not None, 'need <func_name> for debug mode: %s' % command
            return self.__func_dict[func_name]['DEBUG']

        try:
            self.__conn.reset_input_buffer()
            self.__conn.write(command.encode('utf-8'))
            self.__conn.flush()
            self.logger.debug('SEND: %s' % command.encode('utf-8'))
            
            recv_str = ''
            while True:
                if self.__conn.in_waiting:
                    recv_str = self.__conn.read(self.__conn.in_waiting).decode('utf-8')
                    break

            # 若前一返回没被取走, 也没有被reset_input_buffer, 可能拿到xxx;xxx;的返回
            recv_str = recv_str.split(';')[-2]
            assert recv_str <> err_flag, 'error command result.'
        except AssertionError, e:
            self.logger.warning(e)
            return
        except IOError, e:      # serial.SerialException以及IDError合并
            self.__conn.close()
            self.logger.error(e)
            return
        else:
            return recv_str     # ';'可省略

    def cmd_w(self, command, debug=False):
        ''' 
        SET命令, 返回是否执行成功(失败返回None), 可能的异常:
        串口未开启, 写入超时, 写入时发生异常. write命令被write_timeoout配置.
        '''
        
        # DEBUG 模式, 只打日志不执行.
        if debug:
            self.logger.debug('[DEBUG]: %s' % command)
            return len(command)

        try:
            # 发送命令后, 将缓冲区全部写入清空
            self.__conn.write(command.encode('utf-8'))
            self.__conn.flush()
            self.logger.debug('SEND: %s' % command.encode('utf-8'))
        except serial.SerialException, e:
            self.__conn.close()
            self.logger.error('serial error when write: %s' % command)
            self.logger.error(e)
        else:
            return True

    def func_exec(self, func_name, debug=False, skip_check=False, **kwargs):
        ''' 
        执行相应的函数功能, kwargs对应配置文件中DIM或CONVERT段中的参数 
        说明:
        1. skip_check: 跳过各种检查(参数未替换匹配), 不尝试模糊匹配, 需保证调用正确
        2. debug: 调试模式, 该模式下GET命令根据预设的DEBUG值解析返回, SET命令仅打印
        3. 执行前需要检查连接是否存在, 不在cmd_w或cmd_rw中执行, 以减少消耗.
        4. GET命令返回解析后的字典, SET命令返回是否执行成功
        4. 本函数所有异常情况, 均返回None, 由调用方进行识别处理.
        '''
        
        # 非DEBUG模式下, 若串口未打开, 尝试一次打开, 成功则继续, 否则返回报错.
        if not debug and not self.__conn.is_open:
            time.sleep(2)       # 避免频繁尝试重连
            if not self.connect():
                return

        func_name = func_name.upper()

        func_name_pass = False
        if not skip_check:
            # 支持不完整命令, 若XX+'_GET'/XX+'_SET'仅有一个, 可省略, 否则返回报错
            if not func_name.endswith('_GET') and not func_name.endswith('_SET'):
                try_get = self.__func_dict.has_key(func_name+'_GET')
                try_set = self.__func_dict.has_key(func_name+'_SET')
                if try_get and try_set:
                    self.logger.error('ambigious func: %s' % func_name)
                    return
                elif try_get or try_set:
                    func_name_pass = True   # 避免补全后重复检查has_key
                    func_name = func_name + '_GET' if try_get else func_name + '_SET'
                else:
                    self.logger.error('unknown func: %s' % func_name)
                    return

        self.logger.debug('FUNC_EXEC: %s' % func_name)

        if func_name_pass or skip_check or self.__func_dict.has_key(func_name):
            if func_name.endswith('_GET'):
                # _GET类: 按READ方式(先发后收)执行命令CMD, 将返回结果按照转换配置完成转换
                cmd_ret = {}
                ret = self.cmd_rw(self.__func_dict[func_name]['CMD'], debug, func_name)
                if ret:
                    for k,v in self.__func_dict[func_name]['RET'].iteritems():
                        # 按照RET部分配置, 截取结果, 对每个参数, 按顺序尝试: DIM(转码), CONVERT(值转换, 整型)或直接返回
                        ret_seg = ret[eval(v)[0]:eval(v)[1]]

                        if self.__func_dict[func_name].get('DIM') is not None and self.__func_dict[func_name].get('DIM').get(k) is not None:
                            cmd_ret[k] = self.__func_dict[func_name]['DIM'][k].get(ret_seg, 'UNKNOWN')
                        elif self.__func_dict[func_name].get('CONVERT') is not None and self.__func_dict[func_name].get('CONVERT').get(k) is not None:
                            # 目前值转换格式只允许转换为整型, 用于数值类返回
                            cmd_ret[k] = int(round(eval(self.__func_dict[func_name]['CONVERT'][k].replace('x', str(int(ret_seg))))))
                        else:
                            cmd_ret[k] = ret_seg

                        self.logger.debug('[%s: %s] >> [%s:%s]' % (func_name, k, ret_seg, str(cmd_ret[k])))
                    return cmd_ret
                else:
                    self.logger.error('FUNC_EXEC_GET return error: %s' % (func_name))
            elif func_name.endswith('_SET'):
                command = self.__func_dict[func_name]['CMD']
                for k,v in kwargs.iteritems():  
                    # 将函数入参转换格式后进行替换, 按顺序尝试: DIM(转码), CONVERT(值转换)或直接替换
                    if self.__func_dict[func_name].get('DIM') is not None and self.__func_dict[func_name]['DIM'].get(k) is not None:
                        arg_code = self.__func_dict[func_name]['DIM'][k].get(v)
                        assert  arg_code is not None and not arg_code.strip().isspace(), 'no [%s] in DIM: %s - %s' % (v, func_name, k)
                        command = command.replace('{$'+k+'}', arg_code)
                    elif self.__func_dict[func_name].get('CONVERT') is not None and self.__func_dict[func_name]['CONVERT'].get(k) is not None:
                        assert self.__func_dict[func_name]['CONVERT'][k].get('EXPS') is not None \
                            and self.__func_dict[func_name]['CONVERT'][k].get('FORM') is not None, 'func [%s] CONVERT with invalid config.' % func_name

                        conv_val = int(round(eval(self.__func_dict[func_name]['CONVERT'][k]['EXPS'].replace('x', str(v)))))
                        form = self.__func_dict[func_name]['CONVERT'][k]['FORM'].split('|')

                        if form[0] == 'L':
                            var_str = str(conv_val).ljust(int(form[1]), form[2])
                        elif form[0] == 'R':
                            var_str = str(conv_val).rjust(int(form[1]), form[2])
                        else:   # 若FORM无法识别, 则默认将转换后的数值作为字符串直接使用
                            var_str = str(conv_val)
                        command = command.replace('{$%s}' % k, var_str)
                    else:
                        command = command.replace('{$%s}' % k, str(v))
                
                # 检查是否有未替换的参数
                if not skip_check:
                    assert command.find('{$') < 0, 'some vars not been replaced: %s' % command

                return self.cmd_w(command, debug)
            else:
                self.logger.error('FUNC_EXEC not a _SET or _GET: %s' % func_name)
        else:
            self.logger.error('FUNC_EXEC unknown: %s' % func_name)
        
        return
    
    ############################ 增益值 ############################

    def af_gain(self, val=None):
        return self.func_exec('AF_GAIN_SET', VAL=val) if val else self.func_exec('AF_GAIN_GET')

    def rf_gain(self, val=None):
        return self.func_exec('RF_GAIN_SET', VAL=val) if val else self.func_exec('RF_GAIN_GET')
    
    def mic_gain(self, val=None):
        return self.func_exec('MIC_GAIN_SET', VAL=val) if val else self.func_exec('MIC_GAIN_GET')
    
    def vox_gain(self, val=None):
        return self.func_exec('VOX_GAIN_SET', VAL=val) if val else self.func_exec('VOX_GAIN_GET')

    ############################ 设备功能 ############################

    def agc(self, mode=None):
        return self.func_exec('AGC_SET', MODE=mode) if mode else self.func_exec('AGC_GET')

    def att(self, status=None):
        return self.func_exec('ATT_SET', STATUS=status) if status else self.func_exec('ATT_GET')
    
    def atu_get(self, status=None):
        return self.func_exec('ATU_SET', STATUS=status) if status else self.func_exec('ATU_GET')

    def ipo(self, status=None):
        return self.func_exec('IPO_SET', STATUS=status) if status else self.func_exec('IPO_GET')
    
    def bk_in(self, status=None):
        return self.func_exec('BREAK_IN_SET', STATUS=status) if status else self.func_exec('BREAK_IN_GET')
    
    def contour_get(self):
        return self.func_exec('CONTOUR_GET')
    
    def monitor(self, status=None):
        return self.func_exec('MONITOR_SET', STATUS=status) if status else self.func_exec('MONITOR_GET')
    
    def narrow(self, status=None):
        return self.func_exec('NARROW_SET', STATUS=status) if status else self.func_exec('NARROW_GET')
    
    def nb_get(self):
        return self.func_exec('NB_GET')

    def nr_get(self):
        return self.func_exec('NR_GET')

    def prc_get(self):
        return self.func_exec('SPEECH_PROCESSOR_GET')

    def shift_get(self):
        return self.func_exec('IF_SHIFT_GET')
    
    def split_get(self):
        return self.func_exec('SPLIT_GET')
    
    def vox_get(self):
        return self.func_exec('VOX_GET')

    def rx_get(self):
        return self.func_exec('RX_GET')

    def tx_get(self):
        return self.func_exec('TX_GET')

    def hi_swr_get(self):
        return self.func_exec('HI_SWR_GET')

    ############################ VFO操作 ############################
 
    def vfo_info_new(self, vfo):
        if vfo == 'A':
            cmd = 'IF;'
        elif vfo == 'B':
            cmd = 'OI;'
        
        ret = self.cmd_rw(cmd)
        # CHANNEL: 2,5          # P1
        # FREQ: 5,14            # P2
        # CLAR_DIRECT: 14,15    # P3
        # CLAR_OFFSET: 15,19    # P3
        # CLAR_STATUS: 19,20    # P4
        # MODE: 21,22           # P6
        # CH_TYPE: 22,23        # P7
        # CTCSS: 23,24          # P8
        # DIFF: 26,27           # P10
        mode_list = {
            '1': 'LSB'
            ,'2': 'USB'
            ,'3': 'CW-U'
            ,'4': 'FM'
            ,'5': 'AM'
            ,'6': 'RTTY-LSB'
            ,'7': 'CW-R'
            ,'8': 'DATA-LSB'
            ,'9': 'RTTY-USB'
            ,'A': 'DATA-FM'
            ,'B': 'FM-N'
            ,'C': 'DATA-USB'
            ,'D': 'AM-N'
            ,'E': 'C4FM'
        }
        return {
            'FREQ': ret[5:14],
            'CLAR_DIRECT': ret[14:15],
            'CLAR_OFFSET': ret[15:19],
            'CLAR_STATUS': 'OFF' if ret[19:20] == '0' else 'ON',
            'MODE': mode_list[ret[21:22]]
            }

def find_secret_command():
    cmds = [chr(a)+chr(b)+c+';' for a in range(65,91) for b in range(65,91) for c in ('','0')]
    a = RIG_CREATOR()
    a.show_ports()
    rig = a.get('FT-891')
    rig.connect('/dev/ttyUSB0', 38400)
    for cmd in cmds:
        rig.cmd_rw_test(cmd)

def demo():
    # 设备连接操作示例
    
    a = RIG_CREATOR()       # 创建设备工厂类, 准备设备配置
    a.show_ports()          # 打印所有可用串口

    rig = a.get('FT-891')   # 使用工厂类创建指定型号设备

    rig.connect('/dev/ttyUSB0', 38400)  # 连接USB串口上连接的设备
    if not rig.connect_status():
        print 'Connect fail.'
        return

    # while 1:
    #     print rig.connect_status()
    #     freq_a = rig.func_exec('VFO_A_FREQ_GET')
    #     freq_b = rig.func_exec('VFO_B_FREQ_GET')
    #     if freq_a and freq_b:
    #         print 'A: %s   B:%s' % (
    #             freq_a.get('FREQ','')
    #             ,freq_b.get('FREQ','')
    #             )

    # 可以这样调用某种功能, 所有可用功能请查阅 YEASU_CAT3.yaml
    rig.func_exec('VFO_A_GET')               # GET
    rig.func_exec('VFO_A_GET', debug=True)   # GET的调试功能, 会认为设备返回[DEBUG]中的数据, 然后解析返回, 测试用
    rig.func_exec('AF_GAIN_SET', VAL=10)     # SET, 参数名称参考配置文件, 如YEASU_CAT3.yaml

    cmds = rig.get_func()                   # 获取全部命令的配置
    for k in cmds.keys():
        if k.endswith('_GET'):
            rig.func_exec(k, debug=False)    # 批量测试所有GET命令

if __name__ == '__main__':
    demo()