# T10 Gateway 控制面

## 1. 任务目标

本任务用于借鉴 OpenClaw Gateway 网关模块，为 RootSeeker V2 建立统一控制面。

Gateway 不只是 API 层，而是负责连接：

- UI
- CLI
- Worker
- Scheduler
- Agent Runtime
- Channel Runtime

参考文档：

- `/Users/beisen/PycharmProjects/openclaw-analysis/06-Gateway网关模块分析.md`

---

## 2. 范围

本任务覆盖：

- Gateway Protocol
- Request / Response / Event 三类帧
- WebSocket / HTTP 接入
- 连接握手
- 事件广播
- Session 订阅
- Gateway Methods

本任务不覆盖：

- 完整前端 UI
- 多数据中心网关集群

---

## 3. 输入

- `CaseEvent`
- `AgentEvent`
- `ToolEvent`
- `GatewayRequest`
- `ClientConnectParams`

---

## 4. 输出

- `GatewayResponse`
- `GatewayEventFrame`
- `Subscription`
- `BroadcastResult`

---

## 5. 一级拆解

### `T10.1` Gateway 协议

定义请求帧、响应帧、事件帧。

### `T10.2` Gateway Server

提供 HTTP / WebSocket 接入。

### `T10.3` Gateway Methods

统一注册控制面方法。

### `T10.4` 广播与订阅

把 Case 和 Agent 事件推送给客户端。

---

## 6. 二级拆解

## 6.1 `T10.1` Gateway 协议

### 帧类型

- `RequestFrame`
- `ResponseFrame`
- `EventFrame`

### 类文件任务

- `gateway/protocol.py`
- `gateway/errors.py`

## 6.2 `T10.2` Gateway Server

### 职责

- 接收连接
- 握手认证
- 管理客户端
- 路由请求

### 类文件任务

- `gateway/server.py`
- `gateway/connection.py`

## 6.3 `T10.3` Gateway Methods

### 方法分类

- `case.*`
- `skill.*`
- `tool.*`
- `plugin.*`
- `channel.*`
- `cron.*`
- `system.*`

### 类文件任务

- `gateway/method_registry.py`
- `gateway/methods/`

## 6.4 `T10.4` 广播与订阅

### 事件类型

- `case.changed`
- `case.step.changed`
- `agent.event`
- `tool.called`
- `approval.requested`
- `cron.job.changed`

### 类文件任务

- `gateway/broadcaster.py`
- `gateway/subscriptions.py`

---

## 7. 风险

- 如果 Gateway 只是普通 HTTP API，长任务状态和实时事件会难以表达
- 如果事件帧没有统一结构，UI、CLI、Worker 会各自解析一套事件
- 如果协议没有版本，后续兼容会很痛苦

---

## 8. 验收标准

- Gateway 能处理请求和响应
- Gateway 能推送事件
- 客户端能订阅 Case 或 Agent 事件
- Gateway 方法可插件化注册

---

## 9. 推荐实施顺序

1. 定义协议帧
2. 实现方法注册
3. 实现 HTTP Gateway
4. 实现 WebSocket Gateway
5. 接入事件广播
