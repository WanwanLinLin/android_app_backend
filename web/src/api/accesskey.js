import CryptoJS from 'crypto-js'

const APP_KEY = import.meta.env.VITE_APP_KEY || ''

/**
 * 构造 validate_stream_accesskey 所需的对称加密请求头（需求 4）。
 * 后端算法（utils/common/auth.py）：
 *   token = SHA1( `${time_stamp}\t${app_key}` )，time_stamp 为毫秒时间戳
 *   请求需带 header: dk = time_stamp, token = token
 * 后端还会校验时间戳与服务器时间差 <= 50s，故每次请求实时生成。
 */
export function accesskeyHeaders() {
  const ts = String(Date.now())
  const token = CryptoJS.SHA1(`${ts}\t${APP_KEY}`).toString(CryptoJS.enc.Hex)
  return { dk: ts, token }
}
