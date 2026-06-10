# -*- coding: utf-8 -*-
import os
import binascii


# 生成一串指定长度的随机号码
def create_numbering(length=24):
    s = binascii.b2a_base64(os.urandom(length))[:-1].decode('utf-8')
    for x in ['+', '=', '/', '?', '&', '%', "#"]:
        s = s.replace(x, "")
    return s


if __name__ == "__main__":
    print(create_numbering())