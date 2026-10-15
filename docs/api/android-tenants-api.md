# 接口文档：按管理员账号获取租户列表

> 面向安卓端对接方 · 版本 V3.5.0 · 更新日期 2026-10-15

---

## 0. 重要声明：业务逻辑已全面切换为 tenant_id，不再使用 user_id

**这是本次对接最需要理解的一点，请先读完本节再看接口细节。**

后端在近期重构中重新划分了 `User` 与 `Tenant` 两张表的职责，业务归属主体已经从 `User` 迁移到 `Tenant`：

| 概念 | 表 | 现在承担的职责 | 是否承载业务数据 |
|---|---|---|---|
| **管理员账号** | `User`（主键 `User.id`，即 `user_id`） | **只做两件事**：后台登录鉴权、Tenant 的生命周期管理（增删改查） | **否** |
| **业务租户** | `Tenant`（主键 `Tenant.id`，即 `tenant_id`） | 数字人运行时的实际归属主体：可用资源（TTS / ASR / LLM / 数字人形象 / 对话模板）、默认资源配置、Agent 会话等全部挂在它下面 | **是** |

具体含义：

1. **`user_id` 现在只是一个"归属管理员"的标记列**，存在于 `Tenant.user_id`，语义是"这个租户归属于哪个后台管理员"。它可以为 `NULL`（表示该租户尚未归属任何管理员）。它**不再**被用来查找资源、配置或会话。
2. **所有业务链路一律走 `tenant_id`**：
   - `SourceList.tenant_id` → `Tenant.id`（租户持有哪些资源）
   - `AgentSessionManagement.tenant_id` → `Tenant.id`（会话归属）
3. **终端（安卓设备）对外的业务身份标识是 `Tenant.tenantname`（租户名字符串），不是 `User.username`。** 后端在收到 `tenantname` 后内部先解析出 `Tenant.id`，再用 `tenant_id` 做后续所有查询。安卓端**不需要**（也**不应该**）在自己的业务逻辑里传 `user_id`。
4. **本项目不使用数据库外键约束**，`Tenant.user_id`、`SourceList.tenant_id` 等引用列的完整性由应用层校验保证。安卓端不要假设"删了管理员，其下租户会自动级联处理"——实际行为是租户的 `user_id` 变成一个悬空值，租户本身及其资源绑定依然存在。
5. **兼容性别名**：为了不打断已在运行的旧版本终端，部分接口同时接受 `username` 参数，但服务端按 `tenantname or username` 处理——也就是说，那里语义上的 `username` **就是租户名**，与 `User.username` 无关。新接入的安卓版本请统一使用 `tenantname` 参数名，不要继续使用 `username` 表示租户。

一句话总结给安卓端：

> **登录用管理员账号（`User.username`）→ 调本接口拿到该账号名下的租户列表 → 之后所有业务接口一律使用租户身份 `tenantname`（及其 `Tenant.id`）。`user_id` 只做展示/归属判断用，不参与业务查询。**

---

## 1. 服务地址

| 项 | 值 |
|---|---|
| 协议 | HTTP |
| 主机 | `192.168.1.52` |
| 端口 | `8852` |
| Base URL | `http://192.168.1.52:8852` |
| 在线文档（Swagger） | `http://192.168.1.52:8852/digitalhuman/api/v1` |

CORS 已放开（`allow_origins=["*"]`），安卓端可直接跨域调用。

---

## 2. 接口定义

### GET /v1/user/tenants/{username}

按**后台管理员账号名**获取该账号名下的**租户列表**。这是安卓端的入口接口：设备用一个管理员账号登录后调用它，得到自己可操作的租户身份。

- **HTTP 方法**：`GET`
- **路径**：`/v1/user/tenants/{username}`
- **Content-Type**：无请求体
- **响应 Content-Type**：`application/json`
- **鉴权**：对称加密（`dk` + `token` 请求头），**不是** JWT，详见第 3 节

#### 2.1 路径参数

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `username` | string | 是 | **后台管理员账号名**，对应 `User.username`（例如 `hopesen`、`originpi`）。注意：这里是管理员账号，**不是**租户名 `tenantname`。二者当前恰好同名，但语义不同，不要混用。含中文或特殊字符时必须做 URL Encode。 |

#### 2.2 查询参数

无。

#### 2.3 请求头

| 请求头 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `dk` | string | 是 | 请求时刻的**毫秒级** Unix 时间戳，十进制字符串，如 `1760494800000` |
| `token` | string | 是 | `SHA1(dk + "\t" + app_key)` 的小写十六进制摘要，见第 3 节 |

`dk` 与 `token` 缺任何一个 → 鉴权失败。

#### 2.4 后端处理逻辑（便于排查问题）

```
1. 校验 dk / token（对称加密鉴权）
2. 按 username 查 User 表，过滤条件：is_delete 为 NULL 或 False
   - 查不到 → 返回 code=400, msg="user not exist", data=null
3. 按 Tenant.user_id == User.id 查租户列表，过滤 is_delete 为 NULL 或 False
4. 返回租户详情列表（可能为空数组）
```

**没有排序保证**（SQL 未加 `ORDER BY`）。安卓端若需要固定顺序，请在客户端按 `id` 或 `tenantname` 自行排序。

---

## 3. 鉴权方式：对称加密 token（与 Web 后台的 JWT 相互独立）

本接口与租户管理类接口刻意使用两套独立鉴权：

| 通道 | 鉴权 | 使用方 |
|---|---|---|
| `/v1/user/tenants/{username}`、`/v1/stream/*`、WebSocket | 请求头 `dk` + `token`（对称加密） | **安卓端 / 终端设备** |
| `/v1/tenant/*`、`/v1/user/list`、`/v1/user/logout` | `Authorization: Bearer <JWT>`（由 `/v1/user/login` 签发） | Web 管理后台 |

安卓端**只需要**关心 `dk` + `token` 这一套，不需要登录拿 JWT。

### 3.1 token 生成算法

```
text  = <毫秒时间戳> + "\t" + app_key        // \t 是 ASCII 制表符 (0x09)，不是空格
token = SHA1(text)                            // 结果取小写十六进制，40 位
```

- `app_key`：由后端分配给终端的密钥，存放在服务端 Redis 的列表 `hps_apikey` 中（形如 `hps_xxxxxxxxxxxxxxxxxxxxx`）。
- 时间戳必须是**毫秒**（13 位）。用秒级时间戳会导致时间窗校验必然失败。

### 3.2 服务端校验规则（务必对齐）

1. 取当前毫秒时间 `now`，若 `now - dk > 50000`（即 **超过 50 秒**）→ 直接判定失败。
   - 只校验"不旧于 50 秒"，**不校验未来时间**。但请不要把时间戳写成未来值。
   - 因此 `dk`/`token` 可以复用，但**不要长期缓存**；建议每次请求现算。
   - 终端设备**系统时间必须准确**（NTP 同步），否则会出现"签名正确却 401"的疑难问题。
2. 遍历 Redis 列表 `hps_apikey` 中的每一个 `app_key`，逐个计算 `SHA1(dk + "\t" + app_key)`，与请求头 `token` 比对，命中即通过。
   - 即：服务端支持多个合法 `app_key` 并存，安卓端只需持有其中一个。

### 3.3 ⚠️ 对接前置条件（当前阻塞项）

服务端 Redis `192.168.1.52:6390` 的列表 **`hps_apikey` 目前为空**（2026-10-15 实测 `LLEN hps_apikey = 0`）。这意味着**当前任何 token 都会校验失败**。

上线前必须由后端/运维执行一次：

```bash
redis-cli -h 192.168.1.52 -p 6390 RPUSH hps_apikey "<分配给终端的 app_key>"
```

安卓端联调时如果 `token` 算法确认无误仍然鉴权失败，**第一顺位排查这一项**，其次排查设备时间偏差。

---

## 4. 响应结构

外层是全站统一包装 `GeneticResponse`：

| 字段 | 类型 | 说明 |
|---|---|---|
| `code` | int | `200` 成功；`400` 账号不存在；`401` 鉴权失败；`500` 服务端异常 |
| `msg` | string | `ok` 或错误描述 |
| `data` | array \| null | 租户对象数组；失败时为 `null` |

`data` 数组每个元素（租户详情）：

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | int | **`Tenant.id`，即 `tenant_id`**——租户主键 |
| `user_id` | int \| null | **归属管理员的 `User.id`**。⚠️ 见第 0 节：这**只**是归属标记，可能为 `null`（未归属），**不要**用它做业务查询 |
| `tenantname` | string \| null | **租户名，终端业务身份标识**。后续所有业务接口都用它（对应 `SourceList.tenant_id` 所属租户） |
| `nickname` | string \| null | 真实姓名 |
| `job` | string \| null | 工作描述 |
| `phone_number` | string \| null | 电话号码 |

### 4.1 成功响应示例

请求：

```
GET /v1/user/tenants/hopesen HTTP/1.1
Host: 192.168.1.52:8852
dk: 1760494800000
token: 3f2a...（40位sha1）
```

响应（HTTP 200）：

```json
{
  "code": 200,
  "msg": "ok",
  "data": [
    {
      "id": 1,
      "user_id": 1,
      "tenantname": "hopesen",
      "nickname": null,
      "job": null,
      "phone_number": null
    },
    {
      "id": 3,
      "user_id": 1,
      "tenantname": "hopesen-02",
      "nickname": "张三",
      "job": "园区巡检",
      "phone_number": "13800000000"
    }
  ]
}
```

> 实测当前库中数据：`User(id=1, username=hopesen)` 名下有 `Tenant(id=1, tenantname=hopesen)`；`User(id=2, username=originpi)` 名下有 `Tenant(id=2, tenantname=originpi)`。

### 4.2 账号存在但名下无租户

```json
{ "code": 200, "msg": "ok", "data": [] }
```

**这是成功响应，不是错误。** 安卓端要把"空数组"（该账号无租户，需联系管理员开通）与 `code=400`（账号本身不存在）区分处理。

### 4.3 管理员账号不存在

```json
{ "code": 400, "msg": "user not exist", "data": null }
```

### 4.4 鉴权失败

鉴权失败时 `AccessKeyAuthError` 会落到全站兜底异常处理器，实际返回 **HTTP 200**、`code` 为 **500**，`msg` 形如：

```json
{
  "code": 500,
  "msg": "Internal Server Error:  ... AccessKeyAuthError ...",
  "data": null
}
```

> ⚠️ 这是当前实现的实际行为（`AccessKeyAuthError` 未注册专用 handler，被兜底 handler 捕获为 500），并非文档笔误。**HTTP 状态码恒为 200，安卓端必须以响应体里的 `code` 字段作为唯一成败判据，不要依赖 HTTP 状态码。** 建议后端后续为该异常补一个 `code=401` 的专用 handler，届时本文档同步更新。

---

## 5. 调用示例

### 5.1 cURL

```bash
TS=$(date +%s%3N)                                   # 毫秒时间戳
APP_KEY="hps_vgH7n7UCKjVr7k8kmdM"                  # 后端分配的 app_key
TOKEN=$(printf "%s\t%s" "$TS" "$APP_KEY" | sha1sum | awk '{print $1}')

curl -s "http://192.168.1.52:8852/v1/user/tenants/hopesen" \
     -H "dk: ${TS}" \
     -H "token: ${TOKEN}"
```

注意 `printf "%s\t%s"` 中的 `\t` 必须是真实制表符，不能是空格。

### 5.2 Android / Kotlin（Retrofit + OkHttp 拦截器）

```kotlin
// 1) 签名工具
object HpsSign {
    fun sign(appKey: String): Pair<String, String> {          // 返回 (dk, token)
        val ts = System.currentTimeMillis().toString()        // 毫秒，13 位
        val raw = "$ts\t$appKey"                              // \t = 制表符 0x09
        val digest = MessageDigest.getInstance("SHA-1")
            .digest(raw.toByteArray(Charsets.UTF_8))
        val token = digest.joinToString("") { "%02x".format(it) }   // 小写 hex
        return ts to token
    }
}

// 2) OkHttp 拦截器：自动为所有终端接口加签
class HpsAuthInterceptor(private val appKey: String) : Interceptor {
    override fun intercept(chain: Interceptor.Chain): Response {
        val (dk, token) = HpsSign.sign(appKey)
        return chain.proceed(
            chain.request().newBuilder()
                .header("dk", dk)
                .header("token", token)
                .build()
        )
    }
}

// 3) API 声明
interface TenantApi {
    @GET("v1/user/tenants/{username}")
    suspend fun getTenants(
        @Path("username") username: String      // 管理员账号名，非租户名
    ): ApiResp<List<Tenant>>
}

// 4) 数据模型
data class ApiResp<T>(val code: Int, val msg: String, val data: T?)

data class Tenant(
    val id: Int,                        // tenant_id
    @SerializedName("user_id") val userId: Int?,      // 仅归属标记，禁止用于业务查询
    @SerializedName("tenantname") val tenantName: String?,   // ★ 业务身份，后续接口用它
    val nickname: String?,
    val job: String?,
    @SerializedName("phone_number") val phoneNumber: String?
)
```

### 5.3 Java（OkHttp 直调）

```java
long ts = System.currentTimeMillis();
String raw = ts + "\t" + APP_KEY;
byte[] d = MessageDigest.getInstance("SHA-1").digest(raw.getBytes(StandardCharsets.UTF_8));
StringBuilder sb = new StringBuilder();
for (byte b : d) sb.append(String.format("%02x", b));

Request req = new Request.Builder()
    .url("http://192.168.1.52:8852/v1/user/tenants/" + URLEncoder.encode(username, "UTF-8"))
    .header("dk", String.valueOf(ts))
    .header("token", sb.toString())
    .get()
    .build();
```

---

## 6. 推荐对接流程

```
┌────────────────────────────────────────────────────────────────┐
│ 安卓端启动                                                      │
│   │                                                            │
│   ├─ 1. 输入管理员账号 username（User.username）                 │
│   │                                                            │
│   ├─ 2. GET /v1/user/tenants/{username}      ← 本文档接口        │
│   │      ├─ code=400  → 提示"账号不存在"                         │
│   │      ├─ data=[]   → 提示"该账号下暂无租户，请联系管理员开通"    │
│   │      ├─ data 1 条 → 直接选中该租户                           │
│   │      └─ data 多条 → 弹出租户选择列表（显示 tenantname）        │
│   │                                                            │
│   ├─ 3. 本地持久化选中的 tenantname（及 tenant_id 备查）           │
│   │                                                            │
│   └─ 4. 之后所有业务接口一律携带 tenantname，不再出现 user_id：    │
│          POST /v1/stream/getSourceList?tenantname=xxx           │
│          POST /v1/stream/getDefaultSourceConfig?tenantname=xxx  │
│          POST /v1/stream/saveDefaultSourceConfig  {tenantname}  │
│          WS   /v1/stream/recognition?uid=<tenantname>&token=…   │
└────────────────────────────────────────────────────────────────┘
```

要点：

- 租户列表建议在 App 内做缓存 + 下拉刷新，不要每次建会话都重新拉取。
- 多租户场景（一个管理员账号下有多个租户）必须由用户显式选择，选中结果持久化；`Tenant.id` 可作为本地缓存的 key，`tenantname` 作为上报给服务端的业务标识。
- WebSocket 建连参数 `uid` 传的就是 `tenantname`，不是 `username`，也不是 `tenant_id`。

---

## 7. 注意事项与已知坑

1. **成败判据只看响应体 `code`**，HTTP 状态码恒为 `200`（含鉴权失败、服务端异常）。
2. **`dk` 必须是毫秒**；设备时间偏差 > 50 秒会持续鉴权失败，请在 App 内做一次时间偏差自检并提示用户。
3. **`app_key` 是终端内置密钥**，属敏感信息：不要写入日志、不要抓包后外发、不要在崩溃上报里带上。泄露后由后端在 `hps_apikey` 中移除该 key 即可失效。
4. **`hps_apikey` 当前为空**（见 3.3），联调前必须确认后端已写入。
5. **不要用 `user_id` 做业务查询**（第 0 节）。响应里的 `user_id` 仅供"这个租户属于哪个管理员"的展示与判断，且可能为 `null`，安卓端解析时必须按可空处理。
6. **`username`（路径参数，管理员账号）≠ `tenantname`（租户名）**。当前库中恰好同名（`hopesen` / `originpi`），但这是巧合，未来一个管理员可挂多个不同名租户，切勿在代码里互相赋值。
7. **软删除口径**：服务端只返回 `is_delete` 为 `NULL` 或 `False` 的记录（历史数据存在 `NULL`）。安卓端不需要额外过滤，也不要自己传删除标记。
8. **租户资源绑定接口（`/v1/tenant/*`）走 JWT，不属安卓端通道**，是 Web 管理后台职责，安卓端无需对接。
9. 路径参数请做 URL Encode；`tenantname` 建议只使用 ASCII 字符（`String(50)` 长度限制）。
10. **数据无排序保证**，多租户列表请在客户端排序后再展示。

---

## 8. 变更记录

| 日期 | 变更 |
|---|---|
| 2026-10-14 | 业务归属主体由 `User` 迁移至 `Tenant`：`SourceList` / `AgentSessionManagement` 改用 `tenant_id` 关联；`User` 仅保留登录鉴权与租户生命周期管理；本项目不再使用数据库外键约束 |
| 2026-10-14 | 终端侧接口新增 `tenantname` 参数，`username` 保留为兼容别名（服务端按 `tenantname or username` 处理） |
| 2026-10-15 | 首次输出本接口文档，实测确认数据现状与 `hps_apikey` 为空这一阻塞项 |
