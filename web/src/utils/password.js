// 登录口令哈希：与安卓端 LoginScreen.kt 完全一致的方案（见 my_tasks/android-login-api.md）。
// 客户端用内嵌固定盐对明文做 BCrypt(cost=12)，把 60 位哈希放进请求体 password 字段，
// 服务端登录通路①「提交串 == User.hashed_password」直接命中。**永远不把明文密码发出网络。**
//
// 注意：
// - 盐必须与安卓端、以及建号脚本 scripts/create_user.py 的 ANDROID_SALT 完全一致，
//   否则三端哈希对不上会报密码错误。
// - bcryptjs 与 Python bcrypt / jbcrypt 对同一盐同一密码结果一致（2a 修订版）。
import bcrypt from 'bcryptjs'

export const BCRYPT_SALT = '$2a$12$KpX5/PA4FXJkZNsnuYk41.'

/** 明文 → 60 位 BCrypt 哈希（确定性输出）。空串返回空串，交由表单校验拦截。 */
export function hashPassword(plain) {
  if (!plain) return ''
  return bcrypt.hashSync(plain, BCRYPT_SALT)
}
