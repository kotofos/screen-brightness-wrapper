use cases:
N local
N remote N monitors

# new*mult + offset

usage:
python3 master.py -b [1|-1]

PORT = 48653

sample config
{
    'debug': True,
    'global_brightness': 70
    'step': 5
    'hosts':{
        '127.0.0.1': {
            'monitors':
                [
                    {
                        'id': 1,
                        'brightness_offset': 0,
                        'brightness_mult': 1,
                        'contrast_max': 52,
                        'contrast_min': 0,
                        'contrast_norm': 50,
                        'cmd': 'ddccontrol -r {prop} -w {brightness} dev:/dev/i2c-{mon_id}',
                        'brightness_prop_id': '0x10'
                        'contrast_prop_id': '0x12'
                    },
                    {
                        'id': 3,
                        'brightness_offset': -5,
                        'brightness_mult': 1,
                        'contrast_max': 52,
                        'contrast_min': 0,
                        'contrast_norm': 50,
                        'cmd': 'ddccontrol -r {prop} -w {brightness} dev:/dev/i2c-{mon_id}',
                        'brightness_prop_id': '0x10'
                        'contrast_prop_id': '0x12'
                    }
                ]
        },
        '192.168.0.3':{
            'cmd': 'my_cmd',
            'monitors':
            [
                {
                    'id':2,
                    'brightness_offset': 0,
                    'brightness_mult': 1,
                }
            ]
        }
    }
}


delta_s 1
delta = 5
old 70
new 75

new * mult + offset
75*1 + 0

75 * 1 -5