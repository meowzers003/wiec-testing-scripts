# -*- coding: utf-8 -*-
"""
Created on Wed Sept 25 10:51:58 2023

@author: Eraguzin
https://www.caen.it/?downloadfile=5208
https://www.caen.it/products/caen-hv-wrapper-library/

CAENHV_GetSysPropList returns 0 system properties and a null pointer
"""
import sys
import os
import pprint
from enum import IntEnum
from ctypes import c_int, c_float, c_void_p, c_char_p, c_char, c_ushort, pointer, cdll, cast, POINTER, byref, sizeof, c_ulong, c_uint32, c_long, c_short, create_string_buffer, c_uint8

class CAENR8033DM:
    def __init__(self, json_data):
        self.prefix = "CAEN R8033DM"    #Prefix for log messages
        self.error = "Error"            #Listing in the dictionary for when the return is an error
        self.rounding_factor = 2        #Round the return floats to this value
        self.model_id = 13              #13 is the value for the 803X series
        self.comm_protocol = 0          #0 is the value for TCP/IP
        self.slot = 0                   #R8033DM only has one logical slot
        self.board_param_size = 10      #Empirically found that parameter names have max size of 10 characters, needed for pointer casting
        self.ch_name_size = 12          #Empirically found that channel names have a max size of 12 characters, needed for pointer casting
        self.state_size = 30            #Empiracally found that state on/off names have a max size of 30 characters, needed for pointer casting
        self.num_of_channels = 16
        self.board_params = {}
        self.ch_params = {}
        self.json_data = json_data

        try:
            dllpath = os.path.join(os.getcwd(), self.json_data['caenR8033DM_driver'])
            self.libcaenhvwrapper = cdll.LoadLibrary(dllpath)
        except Exception as e:
            print(e)
            sys.exit(f"{self.prefix} --> Could not load CAEN's C library at {dllpath}")

        print(f"{self.prefix} --> CAEN's C library opened at {dllpath}")

        #Integer handler for the connection
        self.caen = c_int()
        #This function always needs to be run first to establish the connection to the device
        return_code = self.libcaenhvwrapper.CAENHV_InitSystem(c_int(self.model_id),
                                                              c_int(self.comm_protocol),
                                                              self.json_data['caenR8033DM'].encode('utf-8'),    #IP address for TCP/IP
                                                              "".encode('utf-8'),                               #Username, unused
                                                              "".encode('utf-8'),                               #Password, unused
                                                              pointer(self.caen))                               #Pointer to returned handle

        self.check_return(return_code, "Initialization Failed", "Connected to Caen R8033D")

        self.get_crate_info()
        #self.get_sys_info()
        self.get_board_info()
        self.get_channel_info()
        #self.get_channel_parameter_value([12,5, 2, 9, 14], "VSet")
        #self.get_channel_name(5)
        #self.get_channel_name([12,5, 2, 9, 14])

        # self.set_board_parameter("BdIlkm", 1)
        # self.get_board_parameter_value("BdIlkm")

        #Turn off any channels that are turned on
        self.set_ch_parameter([0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15], "Pw", [0])
        self.get_channel_parameter_value([0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15], "Pw")
        self.get_channel_parameter_value([0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15], "Status")
        #
        # self.set_ch_parameter([0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15], "IMRange", [1])
        # self.get_channel_parameter_value([0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15], "IMRange")

        #print("Channel properties are:")
        #pprint.pprint(self.ch_params, width = 1)

        #print("Board level properties are:")
        #pprint.pprint(self.board_params, width = 1)

    def __del__(self):
        return_code = self.libcaenhvwrapper.CAENHV_DeinitSystem(self.caen)
        self.check_return(return_code, "Disconnection Failed", "Disconnected")

    #This function gets the information about the crate as a whole, number of slots, channels, etc...
    #In our case, we only have 1 slot. For some reason the description list returns nothing and I can' parse the firmware releases, but those don't matter
    def get_crate_info(self):
        c_num_of_slots = c_ushort()
        c_num_of_channels = POINTER(c_ushort)()
        c_description_list = c_char_p()
        c_model_list = c_char_p()
        c_serial_num_list = POINTER(c_ushort)()
        c_firmware_release_min_list = c_char_p()
        c_firmware_releae_max_list = c_char_p()
        return_code = self.libcaenhvwrapper.CAENHV_GetCrateMap(self.caen,
                                                            byref(c_num_of_slots),
                                                            byref(c_num_of_channels),
                                                            byref(c_model_list),
                                                            byref(c_description_list),
                                                            byref(c_serial_num_list),
                                                            byref(c_firmware_release_min_list),
                                                            byref(c_firmware_releae_max_list))
        self.check_return(return_code, "Failed to get crate map", f"Communicating with Caen {c_model_list.value.decode('utf-8')}, serial number {c_serial_num_list.contents.value} with {c_num_of_slots.value} slots and {c_num_of_channels.contents.value} channels detected")
        self.channel_list = c_num_of_channels.contents

    #This function always returns nothing
    def get_sys_info(self):
        print("system info")
        c_prop_num = c_ushort()
        c_prop_list = c_char_p()
        return_code = self.libcaenhvwrapper.CAENHV_GetSysPropList(self.caen,
                                                            byref(c_prop_num),
                                                            byref(c_prop_list))

        self.check_return(return_code, f"Failed to get system info")
        print(c_prop_num.value)
        par_array = cast(c_prop_list, (POINTER(c_char * 300)))
        for i in range(300):
            print(par_array.contents[i])

    #This function gets the parameters at the full board level, such as board interlock status, or Vmax set by trimmer
    #It then gets the properties of those parameters (Float, read only, etc...) and their current value and makes a dictionary
    def get_board_info(self):
        c_slot_num = c_ushort(self.slot)
        c_bd_param_list = c_char_p()
        #Function takes in a **char type as the parameter list. It will write back an array of char arrays
        return_code = self.libcaenhvwrapper.CAENHV_GetBdParamInfo(self.caen,
                                                            c_slot_num,
                                                            byref(c_bd_param_list))

        self.check_return(return_code, "Failed to get board parameters")

        #Cast as a pointer to 10 char arrays. The type is
        #<class 'caen_r8033dm.LP_c_char_Array_10'>
        #You need to just "know" that each parameter fills 10 chars, either with terminating null characters or gibberish
        #I confirmed by reading out the full memory block, and also through the example C script

        par_array = cast(c_bd_param_list, (POINTER(c_char * self.board_param_size)))

        #If you run par_array.contents, the type is <class 'caen_r8033dm.c_char_Array_10'> and the size is 10
        #But printing it just gives <caen_r8033dm.c_char_Array_10 object at 0x7ff81f8cfe30>
        #And you need to do par_array.contents[0], par_array.contents[1], par_array.contents[2], etc... to get the
        #parameter letter by letter - b'B', b'd', b'I', b'l', b'k', etc...
        #And par_array.contents.value will only give you the first value, as if there was only one char array the pointer pointed to
        #By indexing it as par_array[0] and par_array[1], then par_array[0].contents doesn't exist
        #But type(par_array[0]) is <class 'caen_r8033dm.c_char_Array_10'> and type(par_array[0].value) is <class 'bytes'>
        #So par_array[0].value is b'BdIlk', par_array[1] is b'BdIlkm', par_array[2] is b'BdCtr', etc...
        #These can be decoded through utf-8 or left as is to be passed back to other functions

        i = 0
        board_params = []

        #It's hard to know how many parameters there will be. Even in Caen's example code, they just loop until the pointer to char array is not valid
        #In this Ctypes way, we can go until the resulting 10 char array is either empty '' which happens. Or it's not alphanumeric characters
        #So it's gibberish like \a0\n4 and stuff like that
        while (True):
            result = par_array[i].value.decode('utf-8')
            if (result.isalnum()):
                board_params.append(result)
                i += 1
            else:
                break

        for i in board_params:
            self.get_board_property_info(i)
            self.get_board_parameter_value(i)

    #Every parameter has at least 2 properties, Type (float or long or binary, etc...) and Mode (read only, read/write, etc...)
    #I get those and then depending on the type, there are other implied properties
    def get_board_property_info(self, param):
        c_prop_val = c_ulong()
        return_code = self.libcaenhvwrapper.CAENHV_GetBdParamProp(self.caen,
                                                            c_ushort(self.slot),        #Number of slot
                                                            param.encode('utf-8'),      #Name of the parameter
                                                            "Type".encode('utf-8'),     #Name of the property
                                                            byref(c_prop_val))          #Pointer to result

        self.check_return(return_code, f"Failed to get board parameter {param} type")
        #I'm assuming this will always be the first entry to the board dictionary for this parameter
        self.board_params[param] = {"Type" : self.PropertyType(c_prop_val.value).name}

        return_code = self.libcaenhvwrapper.CAENHV_GetBdParamProp(self.caen,
                                                            c_ushort(self.slot),
                                                            param.encode('utf-8'),
                                                            "Mode".encode('utf-8'),
                                                            byref(c_prop_val))

        self.check_return(return_code, f"Failed to get board parameter {param} mode")
        self.board_params[param]["Mode"] = self.PropertyMode(c_prop_val.value).name

        #Float parameters will always have these properties
        if (self.board_params[param]['Type'] == self.PropertyType.PARAM_TYPE_FLOAT.name):
            c_prop_val = c_float()
            return_code = self.libcaenhvwrapper.CAENHV_GetBdParamProp(self.caen,
                                                                c_ushort(self.slot),
                                                                param.encode('utf-8'),
                                                                "Minval".encode('utf-8'),
                                                                byref(c_prop_val))
            self.check_return(return_code, f"Failed to get board parameter {param} Minval")
            self.board_params[param]["Minval"] = c_prop_val.value

            return_code = self.libcaenhvwrapper.CAENHV_GetBdParamProp(self.caen,
                                                                c_ushort(self.slot),
                                                                param.encode('utf-8'),
                                                                "Maxval".encode('utf-8'),
                                                                byref(c_prop_val))
            self.check_return(return_code, f"Failed to get board parameter {param} Maxval")
            self.board_params[param]["Maxval"] = c_prop_val.value

            c_prop_val = c_ushort()
            return_code = self.libcaenhvwrapper.CAENHV_GetBdParamProp(self.caen,
                                                                c_ushort(self.slot),
                                                                param.encode('utf-8'),
                                                                "Unit".encode('utf-8'),
                                                                byref(c_prop_val))
            self.check_return(return_code, f"Failed to get board parameter {param} Unit")
            self.board_params[param]["Unit"] = c_prop_val.value

            c_prop_val = c_short()
            return_code = self.libcaenhvwrapper.CAENHV_GetBdParamProp(self.caen,
                                                                c_ushort(self.slot),
                                                                param.encode('utf-8'),
                                                                "Exp".encode('utf-8'),
                                                                byref(c_prop_val))
            self.check_return(return_code, f"Failed to get board parameter {param} Exp")
            self.board_params[param]["Exp"] = c_prop_val.value

        elif (self.board_params[param]['Type'] == self.PropertyType.PARAM_TYPE_ONOFF.name):
            c_prop_val = (c_char * self.state_size)()
            return_code = self.libcaenhvwrapper.CAENHV_GetBdParamProp(self.caen,
                                                                c_ushort(self.slot),
                                                                param.encode('utf-8'),
                                                                "Onstate".encode('utf-8'),
                                                                c_prop_val)
            self.check_return(return_code, f"Failed to get board parameter {param} Onstate")
            self.board_params[param]["Onstate"] = c_prop_val.value.decode('utf-8')
            return_code = self.libcaenhvwrapper.CAENHV_GetBdParamProp(self.caen,
                                                                c_ushort(self.slot),
                                                                param.encode('utf-8'),
                                                                "Offstate".encode('utf-8'),
                                                                c_prop_val)
            self.check_return(return_code, f"Failed to get board parameter {param} Offstate")
            self.board_params[param]["Offstate"] = c_prop_val.value.decode('utf-8')

    #With the parameter's properties known, we can poll to see what the parameter value is
    #This does that and adds it to the dictionary
    def get_board_parameter_value(self, param):
        if param not in self.board_params:
            sys.exit(f"{self.prefix} --> Tried to access parameter{param} which wasn't in the board parameter list. Board parameter list is {self.board_params}")
        if (('Type' not in self.board_params[param]) or ('Mode' not in self.board_params[param])):
            sys.exit(f"{self.prefix} --> Tried to access parameter{param} which didn't have Type and Mode set up in the board parameter list. Board parameter list is {self.board_params}")
        if (self.board_params[param]['Mode'] == self.PropertyMode.PARAM_MODE_WRONLY):
            sys.exit(f"{self.prefix} --> Trying to read a parameter that is read only. Board parameter list is {self.board_params}")

        if (self.board_params[param]['Type'] == self.PropertyType.PARAM_TYPE_FLOAT.name):
            c_param_val = c_float()
        else:
            c_param_val = c_long()

        return_code = self.libcaenhvwrapper.CAENHV_GetBdParam(self.caen,
                                                            c_ushort(self.slot),
                                                            byref(c_ushort(self.slot)),
                                                            param.encode('utf-8'),
                                                            byref(c_param_val))

        self.check_return(return_code, f"Retrieving value for parameter {param} failed")
        self.board_params[param]["Value"] = c_param_val.value
        return c_param_val.value

    #This function gets the parameters for a representative channel and makes a big dictionary with all channels' properties, permissions and value
    #Parameters are things like the voltae setting, the ramp down speed, the current trigger setting and so on
    #Their properties are things like "Float" or "Binary" or "Read only" or "Max value"
    def get_channel_info(self):
        c_par_num = c_ushort()
        c_par_list = c_char_p()
        return_code = self.libcaenhvwrapper.CAENHV_GetChParamInfo(self.caen,
                                                            c_ushort(self.slot),    #Only 1 slot on this device
                                                            c_ushort(0),            #Default to channel 0 to get all properties for the channels since they're all the same
                                                            byref(c_par_list),      #List of the parameters
                                                            byref(c_par_num))       #Returns the number of parameters. I already know empirically that it's 11. But I find the array size programmatically below anyway

        self.check_return(return_code, f"Failed to get channel info")

        #See comments in board info function for what happens here
        par_array = cast(c_par_list, (POINTER(c_char * self.board_param_size)))
        i = 0
        ch_params = []
        while (True):
            result = par_array[i].value.decode('utf-8')
            if (result.isalnum()):
                ch_params.append(result)
                i += 1
            else:
                break
        #After making a list of all the parameter names, I programmatically ask the instrument for all the properties about that parameter
        #In order to make a big dictionary with every channel's parameters, and their properties and values
        for ch in range(self.num_of_channels):
            for i in ch_params:
                self.get_channel_property_info(ch, i)       #First get the properties of the value, so you know if it's a float, long, etc...
                self.get_channel_parameter_value(ch, i)     #Then use that to get the current value and fill it in

    #Every parameter has at least 2 properties, Type (float or long or binary, etc...) and Mode (read only, read/write, etc...)
    #I get those and then depending on the type, there are other implied properties
    def get_channel_property_info(self, ch, param):
        c_prop_val = c_ulong()
        return_code = self.libcaenhvwrapper.CAENHV_GetChParamProp(self.caen,
                                                            c_ushort(self.slot),        #Slot number
                                                            c_ushort(ch),               #Which channel's properties
                                                            param.encode('utf-8'),      #Name of the parameter
                                                            "Type".encode('utf-8'),     #Name of the property
                                                            byref(c_prop_val))          #Result

        self.check_return(return_code, f"Failed to get channel parameter {param} type")

        #This will always be the first parameter and property in the channel dictionary.
        if (ch not in self.ch_params):
            self.ch_params[ch] = {param: {"Type" : self.PropertyType(c_prop_val.value).name}}
        else:
            self.ch_params[ch].update({param: {"Type" : self.PropertyType(c_prop_val.value).name}})

        return_code = self.libcaenhvwrapper.CAENHV_GetChParamProp(self.caen,
                                                            c_ushort(self.slot),
                                                            c_ushort(ch),
                                                            param.encode('utf-8'),
                                                            "Mode".encode('utf-8'),
                                                            byref(c_prop_val))

        self.check_return(return_code, f"Failed to get channel parameter {param} mode")
        self.ch_params[ch][param]["Mode"] = self.PropertyMode(c_prop_val.value).name
        #Float parameters will always have these properties
        if (self.ch_params[ch][param]['Type'] == self.PropertyType.PARAM_TYPE_FLOAT.name):
            c_prop_val = c_float()
            return_code = self.libcaenhvwrapper.CAENHV_GetChParamProp(self.caen,
                                                                c_ushort(self.slot),
                                                                c_ushort(ch),
                                                                param.encode('utf-8'),
                                                                "Minval".encode('utf-8'),
                                                                byref(c_prop_val))
            self.check_return(return_code, f"Failed to get channel parameter {param} Minval")
            self.ch_params[ch][param]["Minval"] = c_prop_val.value

            return_code = self.libcaenhvwrapper.CAENHV_GetChParamProp(self.caen,
                                                                c_ushort(self.slot),
                                                                c_ushort(ch),
                                                                param.encode('utf-8'),
                                                                "Maxval".encode('utf-8'),
                                                                byref(c_prop_val))
            self.check_return(return_code, f"Failed to get channel parameter {param} Maxval")
            self.ch_params[ch][param]["Maxval"] = c_prop_val.value

            c_prop_val = c_ushort()
            return_code = self.libcaenhvwrapper.CAENHV_GetChParamProp(self.caen,
                                                                c_ushort(self.slot),
                                                                c_ushort(ch),
                                                                param.encode('utf-8'),
                                                                "Unit".encode('utf-8'),
                                                                byref(c_prop_val))
            self.check_return(return_code, f"Failed to get channel parameter {param} Unit")
            self.ch_params[ch][param]["Unit"] = c_prop_val.value

            c_prop_val = c_short()
            return_code = self.libcaenhvwrapper.CAENHV_GetChParamProp(self.caen,
                                                                c_ushort(self.slot),
                                                                c_ushort(ch),
                                                                param.encode('utf-8'),
                                                                "Exp".encode('utf-8'),
                                                                byref(c_prop_val))
            self.check_return(return_code, f"Failed to get channel parameter {param} Exp")
            self.ch_params[ch][param]["Exp"] = c_prop_val.value

            c_prop_val = c_ushort()
            return_code = self.libcaenhvwrapper.CAENHV_GetChParamProp(self.caen,
                                                                c_ushort(self.slot),
                                                                c_ushort(ch),
                                                                param.encode('utf-8'),
                                                                "Decimal".encode('utf-8'),
                                                                byref(c_prop_val))
            self.check_return(return_code, f"Failed to get channel parameter {param} Decimal")
            self.ch_params[ch][param]["Decimal"] = c_prop_val.value
        # elif (self.ch_params[ch][param]['Type'] == self.PropertyType.PARAM_TYPE_ONOFF.name):
        #     c_prop_val = (c_char * self.state_size)()
        #     return_code = self.libcaenhvwrapper.CAENHV_GetBdParamProp(self.caen,
        #                                                         c_ushort(self.slot),
        #                                                         param.encode('utf-8'),
        #                                                         "Onstate".encode('utf-8'),
        #                                                         c_prop_val)
        #     self.check_return(return_code, f"Failed to get board parameter {param} Onstate")
        #     self.ch_params[ch][param]["Onstate"] = c_prop_val.value.decode('utf-8')
        #     return_code = self.libcaenhvwrapper.CAENHV_GetBdParamProp(self.caen,
        #                                                         c_ushort(self.slot),
        #                                                         param.encode('utf-8'),
        #                                                         "Offstate".encode('utf-8'),
        #                                                         c_prop_val)
        #     self.check_return(return_code, f"Failed to get board parameter {param} Offstate")
        #     self.ch_params[ch][param]["Offstate"] = c_prop_val.value.decode('utf-8')

    #With the parameter's properties known, we can poll to see what the parameter value is
    #This does that and adds it to the dictionary
    #This can be called with a single channel or a list of channels because the C function allows both
    #If called with a single int for channel, I make it a list of that one int so it works the same
    def get_channel_parameter_value(self, chns, param, print_meas=False):
        if (isinstance(chns, int)):
            chns = [chns]
        size = len(chns)
        for ch in chns:
            if param not in self.ch_params[ch]:
                sys.exit(f"{self.prefix} --> Tried to access parameter{param} which wasn't in the channel parameter list. Channel {ch} parameter list is {self.ch_params[ch]}")
            if (('Type' not in self.ch_params[ch][param]) or ('Mode' not in self.ch_params[ch][param])):
                sys.exit(f"{self.prefix} --> Tried to access parameter{param} which didn't have Type and Mode set up in the channel parameter list. Channel {ch} parameter list is {self.ch_params[ch]}")
            if (self.ch_params[ch][param]['Mode'] == self.PropertyMode.PARAM_MODE_WRONLY):
                sys.exit(f"{self.prefix} --> Trying to read a parameter that is read only. Channel {ch} parameter list is {self.ch_params[ch]}")
        if (self.ch_params[chns[0]][param]['Type'] == self.PropertyType.PARAM_TYPE_FLOAT.name):
            c_param_val = (c_float * size)()
        else:
            c_param_val = (c_uint32 * size)()
        c_ch_list = (c_ushort * size)()
        for num,ch in enumerate(chns):
            c_ch_list[num] = ch
        return_code = self.libcaenhvwrapper.CAENHV_GetChParam(self.caen,
                                                            c_ushort(self.slot),
                                                            param.encode('utf-8'),      #Parameter to read
                                                            c_ushort(size),             #Number of channels you want to read (say 3)
                                                            byref(c_ch_list),           #Which specific channels you want to read (say 12, 5, and 8 in that order)
                                                            byref(c_param_val))         #Will return that many floats or longs, organized in the way you called it
        if (self.check_return(return_code, f"Retrieving value for channels {chns}, parameter {param} failed") == 0):
            for num,ch in enumerate(chns):
                self.ch_params[ch][param]["Value"] = c_param_val[num]
                if print_meas:
                    print(f"{self.prefix} --> Ch {ch} {param}: {c_param_val[num]}")
        else:
            for ch in chns:
                self.ch_params[ch][param]["Value"] = self.error

        #I realized that upstream functions want this value returned to them
        #Since this function can accept a single value or an array, return what was passed in
        #Floats are rounded to make the comparison for a write easier
        if (len(chns) == 1):
            return c_param_val[0]
        else:
            return [round(i,self.rounding_factor) for i in c_param_val]

    #This is a curious function. You pass in a channel like 5 and it returns "CH05"
    #And you can ask for multiple, say channels 12, 4, and 8. Sure enough, you get "Ch12, Ch04, Ch08"
    #There's a corresponding function that lets you set the name to change it. Whatever that does.
    #Not sure what use it is, but I figured I'd implement it. It runs on the same logic as getting the values of multiple channels parameters
    #However, whenever I use this function with multiple channels, it works. But at the end of the Python program there's a segfault
    def get_channel_name(self, chns):
        if (isinstance(chns, int)):
            chns = [chns]
        size = len(chns)

        c_ch_list = (c_ushort * size)()
        for num,ch in enumerate(chns):
            c_ch_list[num] = ch

        c_ch_name = (c_char_p * size)()
        return_code = self.libcaenhvwrapper.CAENHV_GetChName(self.caen,
                                                            c_ushort(self.slot),
                                                            c_ushort(size),             #Number of channels you want to read (say 3)
                                                            byref(c_ch_list),           #Which specific channels you want to read (say 12, 5, and 8 in that order)
                                                            byref(c_ch_name))
        self.check_return(return_code, f"Failed to get channel Name {chns}")
        par_array = cast(c_ch_name, (POINTER(c_char * self.ch_name_size)))

        #Not sure what the use case of the function is, so I print it and return it
        return_array = []
        for i in range(size):
            print(par_array[i].value.decode('utf-8'))
            return_array.append(i)

        return return_array

    def set_board_parameter(self, param, val):
        if param not in self.board_params:
            sys.exit(f"{self.prefix} --> Tried to write parameter{param} which wasn't in the board parameter list. Board parameter list is {self.board_params}")
        if (('Type' not in self.board_params[param]) or ('Mode' not in self.board_params[param])):
            sys.exit(f"{self.prefix} --> Tried to write parameter{param} which didn't have Type and Mode set up in the board parameter list. Board parameter list is {self.board_params}")
        if (self.board_params[param]['Mode'] == self.PropertyMode.PARAM_MODE_RDONLY):
            sys.exit(f"{self.prefix} --> Trying to write a parameter that is read only. Board parameter list is {self.board_params}")

        if (self.board_params[param]['Type'] == self.PropertyType.PARAM_TYPE_FLOAT.name):
            c_param_val = c_float(val)
        else:
            c_param_val = c_long(val)
        print(c_param_val)

        return_code = self.libcaenhvwrapper.CAENHV_SetBdParam(self.caen,
                                                            c_ushort(self.slot),
                                                            byref(c_ushort(self.slot)),
                                                            param.encode('utf-8'),
                                                            byref(c_param_val))

        self.check_return(return_code, f"Failed to write board param {param}")

    #Sets the parameter and value for given channels
    #The channel logic works the same as the get channel parameter value. But the function also allows each channel in the list to have a different value
    #If only one value is given, then I apply that to all the channels. If not, the arrays have to be the same size so each value maps to a channel for writing
    def set_ch_parameter(self, chns, param, vals):
        if (isinstance(chns, int)):
            chns = [chns]
        if (not isinstance(vals, list)):
            vals = [vals]
        if ((len(chns) != len(vals)) and (len(vals) != 1)):
            sys.exit(f"{self.prefix} --> Incorrect use of set_ch_parameter! The number of channels and values you supply must be the same! Or only supply one value!\n\
                     You supplied {chns} channels and {vals} values!")
        size = len(chns)
        for ch in chns:
            if param not in self.ch_params[ch]:
                sys.exit(f"{self.prefix} --> Tried to access parameter{param} which wasn't in the channel parameter list. Channel {ch} parameter list is {self.ch_params[ch]}")
            if (('Type' not in self.ch_params[ch][param]) or ('Mode' not in self.ch_params[ch][param])):
                sys.exit(f"{self.prefix} --> Tried to access parameter{param} which didn't have Type and Mode set up in the channel parameter list. Channel {ch} parameter list is {self.ch_params[ch]}")
            if (self.ch_params[ch][param]['Mode'] == self.PropertyMode.PARAM_MODE_WRONLY):
                sys.exit(f"{self.prefix} --> Trying to read a parameter that is read only. Channel {ch} parameter list is {self.ch_params[ch]}")
        if (self.ch_params[chns[0]][param]['Type'] == self.PropertyType.PARAM_TYPE_FLOAT.name):
            c_param_val = (c_float * size)()
        else:
            c_param_val = (c_uint32 * size)()
        if (len(vals) == 1):
            c_param_val[:] = [vals[0]] * size       #This line is where every channel is set to the same value
        else:
            for num,val in enumerate(vals):
                c_param_val[num] = val
        c_ch_list = (c_ushort * size)()
        for num,ch in enumerate(chns):
            c_ch_list[num] = ch
        return_code = self.libcaenhvwrapper.CAENHV_SetChParam(self.caen,
                                                            c_ushort(self.slot),
                                                            param.encode('utf-8'),      #Parameter to write
                                                            c_ushort(size),             #Number of channels you want to write (say 3)
                                                            byref(c_ch_list),           #Which specific channels you want to write (say 12, 5, and 8 in that order)
                                                            byref(c_param_val))         #The array of values for each channel you're writing to
        self.check_return(return_code, f"Writing value {vals} for channels {chns}, parameter {param} failed")

    #Simple class for checking error responses from the instrument and printing messages if applicable
    def check_return(self, ret, failmessage = None, passmessage = None):
        if (ret != 0):
            if (ret == 2):
                sys.exit(f"{self.prefix} --> Write Error, the CAEN R8033DM is probably not in remote programming mode. Check the panel to set it to 'Remote' rather than 'Local'")
            if (failmessage):
                print(f"{self.prefix} --> {failmessage}")
                sys.exit(f"{self.prefix} --> Attempt to communicate with CAEN R8033DM resulted in error code {hex(ret)}")
            return -1
        else:
            if (passmessage):
                print(f"{self.prefix} --> {passmessage}")
            return 0

    #Enum classes of my reverse engineering what the enums must be in the C DLL
    class PropertyType(IntEnum):
        PARAM_TYPE_FLOAT = 0
        PARAM_TYPE_ONOFF = 1
        PARAM_TYPE_CHSTATUS = 2
        PARAM_TYPE_BDSTATUS = 3

    class PropertyMode(IntEnum):
        PARAM_MODE_RDONLY = 0
        PARAM_MODE_WRONLY = 1
        PARAM_MODE_RDWR = 2
