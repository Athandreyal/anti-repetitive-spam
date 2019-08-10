# stuff relating to managing channels on a server
import discord
from discord.ext import commands
from discord.ext.commands import has_permissions
import time
import functions
import fuzzywuzzy.process
import re
import random

bot_message_expire = functions.message_expire()

# todo: event for role creation, that warns about seeing color in a role - since the bot will strip those when user
#       asks for a color


class Roles(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    colors = {
        'default': 0,
        'none': 0,
        'aliceblue': 0xF0F8FF,
        'antiquewhite 1': 0xFFEFDB,
        'antiquewhite 2': 0xEEDFCC,
        'antiquewhite 3': 0xCDC0B0,
        'antiquewhite 4': 0x8B8378,
        'antiquewhite': 0xFAEBD7,
        'aqua': 0x00FFFF,
        'aquamarine': 0x7FFFD4,
        'aquamarine 1': 0x7FFFD4,
        'aquamarine 2': 0x76EEC6,
        'aquamarine 3': 0x66CDAA,
        'aquamarine 4': 0x458B74,
        'azure': 0xF0FFFF,
        'azure 1': 0xF0FFFF,
        'azure 2': 0xE0EEEE,
        'azure 3': 0xC1CDCD,
        'azure 4': 0x838B8B,
        'banana': 0xE3CF57,
        'beige': 0xF5F5DC,
        'bisque': 0xFFE4C4,
        'bisque 1': 0xFFE4C4,
        'bisque 2': 0xEED5B7,
        'bisque 3': 0xCDB79E,
        'bisque 4': 0x8B7D6B,
        'black': 0x000000,
        'blanchedalmond': 0xFFEBCD,
        'blue': 0x0000FF,
        'blue 1': 0x0000FF,
        'blue 2': 0x0000EE,
        'blue 3': 0x0000CD,
        'blue 4': 0x00008B,
        'blueviolet': 0x8A2BE2,
        'brick': 0x9C661F,
        'brown': 0xA52A2A,
        'brown 1': 0xFF4040,
        'brown 2': 0xEE3B3B,
        'brown 3': 0xCD3333,
        'brown 4': 0x8B2323,
        'burlywood': 0xDEB887,
        'burlywood 1': 0xFFD39B,
        'burlywood 2': 0xEEC591,
        'burlywood 3': 0xCDAA7D,
        'burlywood 4': 0x8B7355,
        'burntsienna': 0x8A360F,
        'burntumber': 0x8A3324,
        'cadetblue': 0x5F9EA0,
        'cadetblue 1': 0x98F5FF,
        'cadetblue 2': 0x8EE5EE,
        'cadetblue 3': 0x7AC5CD,
        'cadetblue 4': 0x53868B,
        'cadmiumorange': 0xFF6103,
        'cadmiumyellow': 0xFF9912,
        'carrot': 0xED9121,
        'chartreuse': 0x7FFF00,
        'chartreuse 1': 0x7FFF00,
        'chartreuse 2': 0x76EE00,
        'chartreuse 3': 0x66CD00,
        'chartreuse 4': 0x458B00,
        'chocolate': 0xD2691E,
        'chocolate 1': 0xFF7F24,
        'chocolate 2': 0xEE7621,
        'chocolate 3': 0xCD661D,
        'chocolate 4': 0x8B4513,
        'cobalt': 0x3D59AB,
        'cobaltgreen': 0x3D9140,
        'coldgrey': 0x808A87,
        'coral': 0xFF7256,
        'coral 1': 0xFF7256,
        'coral 2': 0xEE6A50,
        'coral 3': 0xCD5B45,
        'coral 4': 0x8B3E2F,
        'cornflowerblue': 0x6495ED,
        'cornsilk': 0xFFF8DC,
        'cornsilk 1': 0xFFF8DC,
        'cornsilk 2': 0xEEE8CD,
        'cornsilk 3': 0xCDC8B1,
        'cornsilk 4': 0x8B8878,
        'crimson': 0xDC143C,
        'cyan': 0x00FFFF,
        'cyan 1': 0x00FFFF,
        'cyan 2': 0x00EEEE,
        'cyan 3': 0x00CDCD,
        'cyan 4': 0x008B8B,
        'darkblue': 0x00008B,
        'darkcyan': 0x008B8B,
        'darkgoldenrod': 0xB8860B,
        'darkgoldenrod 1': 0xFFB90F,
        'darkgoldenrod 2': 0xEEAD0E,
        'darkgoldenrod 3': 0xCD950C,
        'darkgoldenrod 4': 0x8B6508,
        'darkgray': 0xA9A9A9,
        'darkgreen': 0x006400,
        'darkkhaki': 0xBDB76B,
        'darkmagenta': 0x8B008B,
        'darkolivegreen': 0x556B2F,
        'darkolivegreen 1': 0xCAFF70,
        'darkolivegreen 2': 0xBCEE68,
        'darkolivegreen 3': 0xA2CD5A,
        'darkolivegreen 4': 0x6E8B3D,
        'darkorange': 0xFF8C00,
        'darkorange 1': 0xFF7F00,
        'darkorange 2': 0xEE7600,
        'darkorange 3': 0xCD6600,
        'darkorange 4': 0x8B4500,
        'darkorchid': 0x9932CC,
        'darkorchid 1': 0xBF3EFF,
        'darkorchid 2': 0xB23AEE,
        'darkorchid 3': 0x9A32CD,
        'darkorchid 4': 0x68228B,
        'darkred': 0x8B0000,
        'darksalmon': 0xE9967A,
        'darkseagreen': 0x8FBC8F,
        'darkseagreen 1': 0xC1FFC1,
        'darkseagreen 2': 0xB4EEB4,
        'darkseagreen 3': 0x9BCD9B,
        'darkseagreen 4': 0x698B69,
        'darkslateblue': 0x483D8B,
        'darkslategray': 0x2F4F4F,
        'darkslategray 1': 0x97FFFF,
        'darkslategray 2': 0x8DEEEE,
        'darkslategray 3': 0x79CDCD,
        'darkslategray 4': 0x528B8B,
        'darkturquoise': 0x00CED1,
        'darkviolet': 0x9400D3,
        'deeppink': 0xFF1493,
        'deeppink 1': 0xFF1493,
        'deeppink 2': 0xEE1289,
        'deeppink 3': 0xCD1076,
        'deeppink 4': 0x8B0A50,
        'deepskyblue': 0x00BFFF,
        'deepskyblue 1': 0x00BFFF,
        'deepskyblue 2': 0x00B2EE,
        'deepskyblue 3': 0x009ACD,
        'deepskyblue 4': 0x00688B,
        'dimgray': 0x696969,
        'dodgerblue': 0x1E90FF,
        'dodgerblue 1': 0x1E90FF,
        'dodgerblue 2': 0x1C86EE,
        'dodgerblue 3': 0x1874CD,
        'dodgerblue 4': 0x104E8B,
        'eggshell': 0xFCE6C9,
        'emeraldgreen': 0x00C957,
        'firebrick': 0xB22222,
        'firebrick 1': 0xFF3030,
        'firebrick 2': 0xEE2C2C,
        'firebrick 3': 0xCD2626,
        'firebrick 4': 0x8B1A1A,
        'flesh': 0xFF7D40,
        'floralwhite': 0xFFFAF0,
        'forestgreen': 0x228B22,
        'fuchsia': 0xFF00FF,
        'gainsboro': 0xDCDCDC,
        'ghostwhite': 0xF8F8FF,
        'gold': 0xFFD700,
        'gold 1': 0xFFD700,
        'gold 2': 0xEEC900,
        'gold 3': 0xCDAD00,
        'gold 4': 0x8B7500,
        'goldenrod': 0xDAA520,
        'goldenrod 1': 0xFFC125,
        'goldenrod 2': 0xEEB422,
        'goldenrod 3': 0xCD9B1D,
        'goldenrod 4': 0x8B6914,
        'gray': 0x808080,
        'gray 1': 0x030303,
        'gray 2': 0x050505,
        'gray 3': 0x080808,
        'gray 4': 0x0A0A0A,
        'gray 5': 0x0D0D0D,
        'gray 6': 0x0F0F0F,
        'gray 7': 0x121212,
        'gray 8': 0x141414,
        'gray 9': 0x171717,
        'gray 10': 0x1A1A1A,
        'gray 11': 0x1C1C1C,
        'gray 12': 0x1F1F1F,
        'gray 13': 0x212121,
        'gray 14': 0x242424,
        'gray 15': 0x262626,
        'gray 16': 0x292929,
        'gray 17': 0x2B2B2B,
        'gray 18': 0x2E2E2E,
        'gray 19': 0x303030,
        'gray 20': 0x333333,
        'gray 21': 0x363636,
        'gray 22': 0x383838,
        'gray 23': 0x3B3B3B,
        'gray 24': 0x3D3D3D,
        'gray 25': 0x404040,
        'gray 26': 0x424242,
        'gray 27': 0x454545,
        'gray 28': 0x474747,
        'gray 29': 0x4A4A4A,
        'gray 30': 0x4D4D4D,
        'gray 31': 0x4F4F4F,
        'gray 32': 0x525252,
        'gray 33': 0x545454,
        'gray 34': 0x575757,
        'gray 35': 0x595959,
        'gray 36': 0x5C5C5C,
        'gray 37': 0x5E5E5E,
        'gray 38': 0x616161,
        'gray 39': 0x636363,
        'gray 40': 0x666666,
        'gray 41': 0x696969,
        'gray 42': 0x6B6B6B,
        'gray 43': 0x6E6E6E,
        'gray 44': 0x707070,
        'gray 45': 0x737373,
        'gray 46': 0x757575,
        'gray 47': 0x787878,
        'gray 48': 0x7A7A7A,
        'gray 49': 0x7D7D7D,
        'gray 50': 0x7F7F7F,
        'gray 51': 0x828282,
        'gray 52': 0x858585,
        'gray 53': 0x878787,
        'gray 54': 0x8A8A8A,
        'gray 55': 0x8C8C8C,
        'gray 56': 0x8F8F8F,
        'gray 57': 0x919191,
        'gray 58': 0x949494,
        'gray 59': 0x969696,
        'gray 60': 0x999999,
        'gray 61': 0x9C9C9C,
        'gray 62': 0x9E9E9E,
        'gray 63': 0xA1A1A1,
        'gray 64': 0xA3A3A3,
        'gray 65': 0xA6A6A6,
        'gray 66': 0xA8A8A8,
        'gray 67': 0xABABAB,
        'gray 68': 0xADADAD,
        'gray 69': 0xB0B0B0,
        'gray 70': 0xB3B3B3,
        'gray 71': 0xB5B5B5,
        'gray 72': 0xB8B8B8,
        'gray 73': 0xBABABA,
        'gray 74': 0xBDBDBD,
        'gray 75': 0xBFBFBF,
        'gray 76': 0xC2C2C2,
        'gray 77': 0xC4C4C4,
        'gray 78': 0xC7C7C7,
        'gray 79': 0xC9C9C9,
        'gray 80': 0xCCCCCC,
        'gray 81': 0xCFCFCF,
        'gray 82': 0xD1D1D1,
        'gray 83': 0xD4D4D4,
        'gray 84': 0xD6D6D6,
        'gray 85': 0xD9D9D9,
        'gray 86': 0xDBDBDB,
        'gray 87': 0xDEDEDE,
        'gray 88': 0xE0E0E0,
        'gray 89': 0xE3E3E3,
        'gray 90': 0xE5E5E5,
        'gray 91': 0xE8E8E8,
        'gray 92': 0xEBEBEB,
        'gray 93': 0xEDEDED,
        'gray 94': 0xF0F0F0,
        'gray 95': 0xF2F2F2,
        'gray 96': 0xF5F5F5,
        'gray 97': 0xF7F7F7,
        'gray 98': 0xFAFAFA,
        'gray 99': 0xFCFCFC,
        'grey': 0x808080,
        'grey 1': 0x030303,
        'grey 2': 0x050505,
        'grey 3': 0x080808,
        'grey 4': 0x0A0A0A,
        'grey 5': 0x0D0D0D,
        'grey 6': 0x0F0F0F,
        'grey 7': 0x121212,
        'grey 8': 0x141414,
        'grey 9': 0x171717,
        'grey 10': 0x1A1A1A,
        'grey 11': 0x1C1C1C,
        'grey 12': 0x1F1F1F,
        'grey 13': 0x212121,
        'grey 14': 0x242424,
        'grey 15': 0x262626,
        'grey 16': 0x292929,
        'grey 17': 0x2B2B2B,
        'grey 18': 0x2E2E2E,
        'grey 19': 0x303030,
        'grey 20': 0x333333,
        'grey 21': 0x363636,
        'grey 22': 0x383838,
        'grey 23': 0x3B3B3B,
        'grey 24': 0x3D3D3D,
        'grey 25': 0x404040,
        'grey 26': 0x424242,
        'grey 27': 0x454545,
        'grey 28': 0x474747,
        'grey 29': 0x4A4A4A,
        'grey 30': 0x4D4D4D,
        'grey 31': 0x4F4F4F,
        'grey 32': 0x525252,
        'grey 33': 0x545454,
        'grey 34': 0x575757,
        'grey 35': 0x595959,
        'grey 36': 0x5C5C5C,
        'grey 37': 0x5E5E5E,
        'grey 38': 0x616161,
        'grey 39': 0x636363,
        'grey 40': 0x666666,
        'grey 41': 0x696969,
        'grey 42': 0x6B6B6B,
        'grey 43': 0x6E6E6E,
        'grey 44': 0x707070,
        'grey 45': 0x737373,
        'grey 46': 0x757575,
        'grey 47': 0x787878,
        'grey 48': 0x7A7A7A,
        'grey 49': 0x7D7D7D,
        'grey 50': 0x7F7F7F,
        'grey 51': 0x828282,
        'grey 52': 0x858585,
        'grey 53': 0x878787,
        'grey 54': 0x8A8A8A,
        'grey 55': 0x8C8C8C,
        'grey 56': 0x8F8F8F,
        'grey 57': 0x919191,
        'grey 58': 0x949494,
        'grey 59': 0x969696,
        'grey 60': 0x999999,
        'grey 61': 0x9C9C9C,
        'grey 62': 0x9E9E9E,
        'grey 63': 0xA1A1A1,
        'grey 64': 0xA3A3A3,
        'grey 65': 0xA6A6A6,
        'grey 66': 0xA8A8A8,
        'grey 67': 0xABABAB,
        'grey 68': 0xADADAD,
        'grey 69': 0xB0B0B0,
        'grey 70': 0xB3B3B3,
        'grey 71': 0xB5B5B5,
        'grey 72': 0xB8B8B8,
        'grey 73': 0xBABABA,
        'grey 74': 0xBDBDBD,
        'grey 75': 0xBFBFBF,
        'grey 76': 0xC2C2C2,
        'grey 77': 0xC4C4C4,
        'grey 78': 0xC7C7C7,
        'grey 79': 0xC9C9C9,
        'grey 80': 0xCCCCCC,
        'grey 81': 0xCFCFCF,
        'grey 82': 0xD1D1D1,
        'grey 83': 0xD4D4D4,
        'grey 84': 0xD6D6D6,
        'grey 85': 0xD9D9D9,
        'grey 86': 0xDBDBDB,
        'grey 87': 0xDEDEDE,
        'grey 88': 0xE0E0E0,
        'grey 89': 0xE3E3E3,
        'grey 90': 0xE5E5E5,
        'grey 91': 0xE8E8E8,
        'grey 92': 0xEBEBEB,
        'grey 93': 0xEDEDED,
        'grey 94': 0xF0F0F0,
        'grey 95': 0xF2F2F2,
        'grey 96': 0xF5F5F5,
        'grey 97': 0xF7F7F7,
        'grey 98': 0xFAFAFA,
        'grey 99': 0xFCFCFC,
        'green': 0x00FF00,
        'green 1': 0x00FF00,
        'green 2': 0x00EE00,
        'green 3': 0x00CD00,
        'green 4': 0x008B00,
        'green 5': 0x008000,
        'greenyellow': 0xADFF2F,
        'honeydew': 0xF0FFF0,
        'honeydew 1': 0xF0FFF0,
        'honeydew 2': 0xE0EEE0,
        'honeydew 3': 0xC1CDC1,
        'honeydew 4': 0x838B83,
        'hotpink': 0xFF69B4,
        'hotpink 1': 0xFF6EB4,
        'hotpink 2': 0xEE6AA7,
        'hotpink 3': 0xCD6090,
        'hotpink 4': 0x8B3A62,
        'indian red': 0xB0171F,
        'indianred': 0xCD5C5C,
        'indianred 1': 0xFF6A6A,
        'indianred 2': 0xEE6363,
        'indianred 3': 0xCD5555,
        'indianred 4': 0x8B3A3A,
        'indigo': 0x4B0082,
        'ivory': 0xFFFFF0,
        'ivory 1': 0xFFFFF0,
        'ivory 2': 0xEEEEE0,
        'ivory 3': 0xCDCDC1,
        'ivory 4': 0x8B8B83,
        'ivoryblack': 0x292421,
        'khaki': 0xF0E68C,
        'khaki 1': 0xFFF68F,
        'khaki 2': 0xEEE685,
        'khaki 3': 0xCDC673,
        'khaki 4': 0x8B864E,
        'lavender': 0xE6E6FA,
        'lavenderblush': 0xFFF0F5,
        'lavenderblush 1': 0xFFF0F5,
        'lavenderblush 2': 0xEEE0E5,
        'lavenderblush 3': 0xCDC1C5,
        'lavenderblush 4': 0x8B8386,
        'lawngreen': 0x7CFC00,
        'lemonchiffon': 0xFFFACD,
        'lemonchiffon 1': 0xFFFACD,
        'lemonchiffon 2': 0xEEE9BF,
        'lemonchiffon 3': 0xCDC9A5,
        'lemonchiffon 4': 0x8B8970,
        'lightblue': 0xADD8E6,
        'lightblue 1': 0xBFEFFF,
        'lightblue 2': 0xB2DFEE,
        'lightblue 3': 0x9AC0CD,
        'lightblue 4': 0x68838B,
        'lightcoral': 0xF08080,
        'lightcyan': 0xE0FFFF,
        'lightcyan 1': 0xE0FFFF,
        'lightcyan 2': 0xD1EEEE,
        'lightcyan 3': 0xB4CDCD,
        'lightcyan 4': 0x7A8B8B,
        'lightgoldenrod': 0xFFEC8B,
        'lightgoldenrod 1': 0xFFEC8B,
        'lightgoldenrod 2': 0xEEDC82,
        'lightgoldenrod 3': 0xCDBE70,
        'lightgoldenrod 4': 0x8B814C,
        'lightgoldenrodyellow': 0xFAFAD2,
        'lightgreen': 0x90EE90,
        'lightgrey': 0xD3D3D3,
        'lightpink': 0xFFB6C1,
        'lightpink 1': 0xFFAEB9,
        'lightpink 2': 0xEEA2AD,
        'lightpink 3': 0xCD8C95,
        'lightpink 4': 0x8B5F65,
        'lightsalmon': 0xFFA07A,
        'lightsalmon 1': 0xFFA07A,
        'lightsalmon 2': 0xEE9572,
        'lightsalmon 3': 0xCD8162,
        'lightsalmon 4': 0x8B5742,
        'lightseagreen': 0x20B2AA,
        'lightskyblue 1': 0xB0E2FF,
        'lightskyblue 2': 0xA4D3EE,
        'lightskyblue 3': 0x8DB6CD,
        'lightskyblue 4': 0x607B8B,
        'lightskyblue': 0x87CEFA,
        'lightslateblue': 0x8470FF,
        'lightslategray': 0x778899,
        'lightsteelblue': 0xB0C4DE,
        'lightsteelblue 1': 0xCAE1FF,
        'lightsteelblue 2': 0xBCD2EE,
        'lightsteelblue 3': 0xA2B5CD,
        'lightsteelblue 4': 0x6E7B8B,
        'lightyellow': 0xFFFFE0,
        'lightyellow 1': 0xFFFFE0,
        'lightyellow 2': 0xEEEED1,
        'lightyellow 3': 0xCDCDB4,
        'lightyellow 4': 0x8B8B7A,
        'lime': 0x00FF00,
        'limegreen': 0x32CD32,
        'linen': 0xFAF0E6,
        'magenta': 0xFF00FF,
        'magenta 1': 0xFF00FF,
        'magenta 2': 0xEE00EE,
        'magenta 3': 0xCD00CD,
        'magenta 4': 0x8B008B,
        'manganeseblue': 0x03A89E,
        'maroon': 0x800000,
        'maroon 1': 0xFF34B3,
        'maroon 2': 0xEE30A7,
        'maroon 3': 0xCD2990,
        'maroon 4': 0x8B1C62,
        'mediumaquamarine': 0x66CDAA,
        'mediumblue': 0x0000CD,
        'mediumorchid': 0xBA55D3,
        'mediumorchid 1': 0xE066FF,
        'mediumorchid 2': 0xD15FEE,
        'mediumorchid 3': 0xB452CD,
        'mediumorchid 4': 0x7A378B,
        'mediumpurple': 0x9370DB,
        'mediumpurple 1': 0xAB82FF,
        'mediumpurple 2': 0x9F79EE,
        'mediumpurple 3': 0x8968CD,
        'mediumpurple 4': 0x5D478B,
        'mediumseagreen': 0x3CB371,
        'mediumslateblue': 0x7B68EE,
        'mediumspringgreen': 0x00FA9A,
        'mediumturquoise': 0x48D1CC,
        'mediumvioletred': 0xC71585,
        'melon': 0xE3A869,
        'midnightblue': 0x191970,
        'mint': 0xBDFCC9,
        'mintcream': 0xF5FFFA,
        'mistyrose': 0xFFE4E1,
        'mistyrose 1': 0xFFE4E1,
        'mistyrose 2': 0xEED5D2,
        'mistyrose 3': 0xCDB7B5,
        'mistyrose 4': 0x8B7D7B,
        'moccasin': 0xFFE4B5,
        'navajowhite': 0xFFDEAD,
        'navajowhite 1': 0xFFDEAD,
        'navajowhite 2': 0xEECFA1,
        'navajowhite 3': 0xCDB38B,
        'navajowhite 4': 0x8B795E,
        'navy': 0x000080,
        'oldlace': 0xFDF5E6,
        'olive': 0x808000,
        'olivedrab': 0x6B8E23,
        'olivedrab 1': 0xC0FF3E,
        'olivedrab 2': 0xB3EE3A,
        'olivedrab 3': 0x9ACD32,
        'olivedrab 4': 0x698B22,
        'orange': 0xFF8000,
        'orange 1': 0xFFA500,
        'orange 2': 0xEE9A00,
        'orange 3': 0xCD8500,
        'orange 4': 0x8B5A00,
        'orangered': 0xFF4500,
        'orangered 1': 0xFF4500,
        'orangered 2': 0xEE4000,
        'orangered 3': 0xCD3700,
        'orangered 4': 0x8B2500,
        'orchid': 0xDA70D6,
        'orchid 1': 0xFF83FA,
        'orchid 2': 0xEE7AE9,
        'orchid 3': 0xCD69C9,
        'orchid 4': 0x8B4789,
        'palegoldenrod': 0xEEE8AA,
        'palegreen': 0x98FB98,
        'palegreen 1': 0x9AFF9A,
        'palegreen 2': 0x90EE90,
        'palegreen 3': 0x7CCD7C,
        'palegreen 4': 0x548B54,
        'paleturquoise': 0xAEEEEE,
        'paleturquoise 1': 0xBBFFFF,
        'paleturquoise 2': 0xAEEEEE,
        'paleturquoise 3': 0x96CDCD,
        'paleturquoise 4': 0x668B8B,
        'palevioletred': 0xDB7093,
        'palevioletred 1': 0xFF82AB,
        'palevioletred 2': 0xEE799F,
        'palevioletred 3': 0xCD6889,
        'palevioletred 4': 0x8B475D,
        'papayawhip': 0xFFEFD5,
        'peachpuff': 0xFFDAB9,
        'peachpuff 1': 0xFFDAB9,
        'peachpuff 2': 0xEECBAD,
        'peachpuff 3': 0xCDAF95,
        'peachpuff 4': 0x8B7765,
        'peacock': 0x33A1C9,
        'peru': 0xCD853F,
        'pink': 0xFFC0CB,
        'pink 1': 0xFFB5C5,
        'pink 2': 0xEEA9B8,
        'pink 3': 0xCD919E,
        'pink 4': 0x8B636C,
        'plum': 0xDDA0DD,
        'plum 1': 0xFFBBFF,
        'plum 2': 0xEEAEEE,
        'plum 3': 0xCD96CD,
        'plum 4': 0x8B668B,
        'powderblue': 0xB0E0E6,
        'purple': 0x800080,
        'purple 1': 0x9B30FF,
        'purple 2': 0x912CEE,
        'purple 3': 0x7D26CD,
        'purple 4': 0x551A8B,
        'raspberry': 0x872657,
        'rawsienna': 0xC76114,
        'red': 0xFF0000,
        'red 1': 0xFF0000,
        'red 2': 0xEE0000,
        'red 3': 0xCD0000,
        'red 4': 0x8B0000,
        'rosybrown': 0xBC8F8F,
        'rosybrown 1': 0xFFC1C1,
        'rosybrown 2': 0xEEB4B4,
        'rosybrown 3': 0xCD9B9B,
        'rosybrown 4': 0x8B6969,
        'royalblue': 0x4169E1,
        'royalblue 1': 0x4876FF,
        'royalblue 2': 0x436EEE,
        'royalblue 3': 0x3A5FCD,
        'royalblue 4': 0x27408B,
        'saddlebrown': 0x8B4513,
        'salmon': 0xFA8072,
        'salmon 1': 0xFF8C69,
        'salmon 2': 0xEE8262,
        'salmon 3': 0xCD7054,
        'salmon 4': 0x8B4C39,
        'sandybrown': 0xF4A460,
        'sapgreen': 0x308014,
        'seagreen': 0x2E8B57,
        'seagreen 1': 0x54FF9F,
        'seagreen 2': 0x4EEE94,
        'seagreen 3': 0x43CD80,
        'seagreen 4': 0x2E8B57,
        'seashell': 0xFFF5EE,
        'seashell 1': 0xFFF5EE,
        'seashell 2': 0xEEE5DE,
        'seashell 3': 0xCDC5BF,
        'seashell 4': 0x8B8682,
        'sepia': 0x5E2612,
        'sgi beet': 0x8E388E,
        'sgi brightgray': 0xC5C1AA,
        'sgi chartreuse': 0x71C671,
        'sgi darkgray': 0x555555,
        'sgi gray 12': 0x1E1E1E,
        'sgi gray 16': 0x282828,
        'sgi gray 32': 0x515151,
        'sgi gray 36': 0x5B5B5B,
        'sgi gray 52': 0x848484,
        'sgi gray 56': 0x8E8E8E,
        'sgi gray 72': 0xB7B7B7,
        'sgi gray 76': 0xC1C1C1,
        'sgi gray 92': 0xEAEAEA,
        'sgi gray 96': 0xF4F4F4,
        'sgi lightblue': 0x7D9EC0,
        'sgi lightgray': 0xAAAAAA,
        'sgi olivedrab': 0x8E8E38,
        'sgi salmon': 0xC67171,
        'sgi slateblue': 0x7171C6,
        'sgi teal': 0x388E8E,
        'sienna': 0xA0522D,
        'sienna 1': 0xFF8247,
        'sienna 2': 0xEE7942,
        'sienna 3': 0xCD6839,
        'sienna 4': 0x8B4726,
        'silver': 0xC0C0C0,
        'skyblue': 0x87CEEB,
        'skyblue 1': 0x87CEFF,
        'skyblue 2': 0x7EC0EE,
        'skyblue 3': 0x6CA6CD,
        'skyblue 4': 0x4A708B,
        'slateblue': 0x6A5ACD,
        'slateblue 1': 0x836FFF,
        'slateblue 2': 0x7A67EE,
        'slateblue 3': 0x6959CD,
        'slateblue 4': 0x473C8B,
        'slategray': 0x708090,
        'slategray 1': 0xC6E2FF,
        'slategray 2': 0xB9D3EE,
        'slategray 3': 0x9FB6CD,
        'slategray 4': 0x6C7B8B,
        'snow': 0xFFFAFA,
        'snow 1': 0xFFFAFA,
        'snow 2': 0xEEE9E9,
        'snow 3': 0xCDC9C9,
        'snow 4': 0x8B8989,
        'springgreen': 0x00FF7F,
        'springgreen 1': 0x00EE76,
        'springgreen 2': 0x00CD66,
        'springgreen 3': 0x008B45,
        'steelblue': 0x4682B4,
        'steelblue 1': 0x63B8FF,
        'steelblue 2': 0x5CACEE,
        'steelblue 3': 0x4F94CD,
        'steelblue 4': 0x36648B,
        'tan': 0xD2B48C,
        'tan 1': 0xFFA54F,
        'tan 2': 0xEE9A49,
        'tan 3': 0xCD853F,
        'tan 4': 0x8B5A2B,
        'teal': 0x008080,
        'thistle': 0xD8BFD8,
        'thistle 1': 0xFFE1FF,
        'thistle 2': 0xEED2EE,
        'thistle 3': 0xCDB5CD,
        'thistle 4': 0x8B7B8B,
        'tomato': 0xFF6347,
        'tomato 1': 0xFF6347,
        'tomato 2': 0xEE5C42,
        'tomato 3': 0xCD4F39,
        'tomato 4': 0x8B3626,
        'turquoise': 0x40E0D0,
        'turquoise 1': 0x00F5FF,
        'turquoise 2': 0x00E5EE,
        'turquoise 3': 0x00C5CD,
        'turquoise 4': 0x00868B,
        'turquoiseblue': 0x00C78C,
        'violet': 0xEE82EE,
        'violetred': 0xD02090,
        'violetred 1': 0xFF3E96,
        'violetred 2': 0xEE3A8C,
        'violetred 3': 0xCD3278,
        'violetred 4': 0x8B2252,
        'warmgrey': 0x808069,
        'wheat': 0xF5DEB3,
        'wheat 1': 0xFFE7BA,
        'wheat 2': 0xEED8AE,
        'wheat 3': 0xCDBA96,
        'wheat 4': 0x8B7E66,
        'white smoke': 0xF5F5F5,
        'white': 0xFFFFFF,
        'yellow': 0xFFFF00,
        'yellow 1': 0xFFFF00,
        'yellow 2': 0xEEEE00,
        'yellow 3': 0xCDCD00,
        'yellow 4': 0x8B8B00,
        'yellowgreen': 0x9ACD32,
    }

    @staticmethod
    async def random_color(bot, guild_id, target_id):
        color = random.choice(list(Roles.colors.keys()))
        hex = Roles.colors[color]
        guild = bot.get_guild(guild_id)
        target = guild.get_member(target_id)
        await Roles.set_color_role(guild, color, hex, target=target, delete=True, remove=True)

    @staticmethod
    def is_color_enabled(guild):
        sql_c = functions.get_database()[0]
        return sql_c.execute('select count(*) from bot_color_enabled where guild=?',
                                      (guild,)).fetchone()[0] > 0

    @staticmethod
    async def prune_roles(bot, guild):
        sql_c, database = functions.get_database()
        roles = [r[0] for r in sql_c.execute('select id from color_roles where guild=?', (guild, )).fetchall()]
        if not roles:
            return
        guild = bot.get_guild(guild)
        removed = []
        for r in roles:
            role = guild.get_role(r)
            if not role:
                removed.append(r)
            else:
                if not role.members:
                    await role.delete(reason='No one is using it')
                    removed.append(r)
        for r in removed:
            sql_c.execute('delete from color_roles where guild=? and id=?', (guild.id, r))
        database.commit()

    @staticmethod
    def get_color_hex(color):
        if '0x' in color and len(color) == 8:
            return color

        color_hex = Roles.colors.get(color, None)
        if color_hex is not None:
            return color_hex
        return None

    @staticmethod
    def get_matches(color, max=20, confidence=70):
        result = fuzzywuzzy.process.extract(color, Roles.colors.keys(), limit=1000)
        result2 = [x for x in result if x[1] >= confidence]
        result = sorted(result2, key=lambda x: x[1], reverse=True)
        matches = len(result)
        import random
        while len(result) > max:
            choice = random.choice(result)
            if random.randint(0, 100) < 100 - choice[1]:
                result.remove(choice)
        result = [x[0] for x in result]
        return matches, result

    @commands.command(pass_context=True, name='colors')
    async def _colors(self, ctx, *args):
        """$colors <color> [limit=int]

        Queries the dictionary for color names that match
        the given color name text - fuzzy logic is used to
        soft match


        Parameters:
        <color>
            required parameter
            a color name soft-matched against the available list
        [max=int]
            optional parameter
            the maximum number of colors to return
            no upper limit, defaults to 20
            not case sensitive

        Usage:
        $colors bleu
            finds the best matches for bleu, obviously blue is one of

        $colors red max 5
            finds the matches for red, returns 5 of those
        """
        color_enabled = Roles.is_color_enabled(ctx.guild.id)
        if not color_enabled:
            return await ctx.send('Sorry, the color functions have not been enabled in this guild.\n\nUse '
                                  '**$setbotcoloring y** to enable them here',
                                  delete_after=functions.bot_message_expire)
        args = list(args)
        kwargs = dict()
        for param in args:
            if re.match('.*(MAX=).*', param.upper()):
                k, v = param.split('=', 1)
                try:
                    kwargs[k] = int(v)
                except ValueError:
                    return await ctx.send(f'{k} must be an integer, not {v}', delete_after=bot_message_expire)
        for k in kwargs:
            args.remove(f'{k}={kwargs[k]}')
        max = kwargs.get('max', 20)
        args = [x for x in args if '=' not in x]
        color = ' '.join(args).lower()
        if not args:
            return await ctx.send('can\'t exactly match names of colors without a name to match against')
        matches, result = self.get_matches(color, max=max)
        if result:
            if matches == 1:
                await ctx.send(f'There was 1 potential match, it is:\n{", ".join(result)}',
                               delete_after=bot_message_expire)
            elif matches > max:
                await ctx.send(f'There were {matches} potential matches, {max} of those are:\n{", ".join(result)}',
                               delete_after=bot_message_expire)
            else:
                await ctx.send(f'There were {matches} potential matches, those are:\n{", ".join(result)}',
                               delete_after=bot_message_expire)
        else:
            await ctx.send(f'There were {matches} potential matches', delete_after=bot_message_expire)

    @commands.command(pass_context=True)
    async def mycolor(self, ctx, *color):  # no permits, anyone can set their own color role
        """$mycolor <color>

        Sets a colored role for the user
        All other colored roles will be dropped


        Parameters:
        <color>
            required parameter
            expected to be either
                a hex value in format 0xabcdef
                a color name matched against 600 available

        Usage:
        $mycolor 0x0000ff
            sets your color to blue.

        $mycolor red
            sets your color to red
        """

        # if they pass a color name, find the hex for the color name,
        #     then find the role with that hex, and if it doesn't exist, create it.
        color_enabled = Roles.is_color_enabled(ctx.guild.id)
        if not color_enabled:
            return await ctx.send('Sorry, the color functions have not been enabled in this guild.\n\nUse '
                                  '**$setbotcoloring y** to enable them here',
                                  delete_after=functions.bot_message_expire)
        sql_c, database = functions.get_database()
        color = ' '.join(color).lower()
        if color == 'random':
            await self.random_color(self.bot, ctx.guild.id, ctx.author.id)
            sql_c.execute('insert or replace into random_color_assignment (guild, user) values (?, ?)',
                          (ctx.guild.id, ctx.author.id))
            database.commit()
            return
        color_hex = self.get_color_hex(color)
        if color_hex is None:
            # see if there are any close matches
            m = 'I am not sure what color you want\n\n'
            m += 'If that were intended to be a hex value, use this format **0xFFFFFF**'

            matches, result = self.get_matches(color, max=5, confidence=70)
            if result:
                m += '\n\nIf that were a color name, did you perhaps mean' + ('one of' if matches > 1 else '') + ': \n'
                m += ', '.join(sorted(result))
                matches -= 5
                if matches > 0:
                    m += f'\nthere were {matches} other possible matches.\n'
                    m += f'use **$color {color}** to see them'

            return await ctx.send(m, delete_after=bot_message_expire)
        sql_c.execute('delete from random_color_assignment where guild=? and user=?', (ctx.guild.id, ctx.author.id))
        database.commit()
        await self.set_color_role(ctx.guild, color, color_hex, target=ctx.author, delete=True, remove=True)

    async def process_random_color_users(self):
        sql_c, database = functions.get_database()
        users = sql_c.execute('select * from random_color_assignment').fetchall()
        for user in users:
            await self.random_color(self.bot, user[0], user[1])


    @staticmethod
    async def set_color_role(guild, color, color_hex, target: discord.Member = None, remove=False, delete=False,
                             except_names=None):
        if except_names is None:
            except_names = []
        # check if we already have a role with that color
        if isinstance(color_hex, str):
            color_int = int(color_hex, 16)
        else:
            color_int = color_hex
        color_role = None
        for role in guild.roles:
            if role.colour.value == color_int:
                if role.name not in except_names:
                    color_role = role

        if color_role is None and color_int > 0:  # make a new color role then
            if color != color_hex:  # gave a color name
                name = color
            else:
                names = [c for c in Roles.colors if Roles.colors[c] == color_int]
                if names:
                    name = names[0]
                else:
                    name = color
            color_role = await guild.create_role(name=name, color=discord.Color(color_int))
            sql_c, database = functions.get_database()
            sql_c.execute('insert or replace into color_roles (guild, id) values (?, ?)', (guild.id, color_role.id))
            database.commit()

        # remove current user color roles
        for r in target.roles:
            if r.color.value != 0:
                if remove:
                    await target.remove_roles(r, reason='User requested this')
                # check if anyone is still using that color role:
                if delete:
                    exists = False
                    for u in guild.members:
                        if r in u.roles:
                            exists = True
                            break
                    if not exists:
                        await r.delete(reason='No one is using it')

        if color_int > 0:
            try:
                await target.add_roles(color_role, reason='User requested this')
            except discord.NotFound:  # process may have deleted it between creation and assignment, try again
                await Roles.set_color_role(guild, color, color_hex, target, remove, delete, except_names)



    @commands.command(pass_context=True, hidden=True)
    @has_permissions(manage_roles=True)
    async def colorise_protocol(self, ctx):
        """$colorise_protocol

        Parameters:
        None

        Usages:
        $colorise_protocol
            will catalog the users colors and will
                assign them a color specific role
        """
        color_enabled = Roles.is_color_enabled(ctx.guild.id)
        if not color_enabled:
            return await ctx.send('Sorry, the color functions have not been enabled in this guild.\n\nUse '
                                  '**$setbotcoloring y** to enable them here',
                                  delete_after=functions.bot_message_expire)
        num = len(ctx.guild.members)
        await ctx.send(f'initiating....\nThis will take {num} seconds to complete\nWill indicate when complete...',
                       delete_after=bot_message_expire)
        names = [r.name for r in ctx.guild.roles]
        for i, member in enumerate(ctx.guild.members):
            color_int = 0
            for role in member.roles:
                if role.color.value:
                    color_int = role.color.value
            color_hex = "0x%0.6X" % color_int
            name = None
            color = None
            for color in Roles.colors.keys():
                if Roles.colors[color] == color_int:
                    name = color
                    break
            if name is None:
                name = color_hex
            await Roles.set_color_role(ctx, name, color_hex, target=member, except_names=names)
            time.sleep(1)
        await ctx.send('colorise protocol completed.')

    @commands.command(pass_context=True)
    @has_permissions(manage_roles=True)
    async def setbotcoloring(self, ctx, arg):
        sql_c, database = functions.get_database()
        enable = functions.boolean(arg)
        if enable:
            sql_c.execute('insert or replace into bot_color_enabled (guild) values (?)', (ctx.guild.id,))
            await ctx.send('Color commands enabled')
        elif enable is None:
            await ctx.send('I do not understand that parameter please use y or n, 1 or 0, t or f')
        else:
            sql_c.execute('delete from bot_color_enabled where guild=?', (ctx.guild.id,))
            await ctx.send('Color commands disabled')


def setup(bot):
    bot.add_cog(Roles(bot))
