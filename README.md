# AI群聊小说 Docker 部署说明

## 项目说明

这是一个基于 `Flask + Vue3 + MySQL` 的小说处理与阅读项目，主要功能包括：

- 上传整本 TXT 小说
- 手动拆分章节
- 调用大模型把章节转换为群聊对话流
- 手机端阅读原文和群聊阅读
- 用户注册、登录、保存各自的大模型配置
- 每个账号只能访问自己的小说、章节、解析结果和阅读记录

## 当前部署结构

`docker compose` 会启动 3 个服务：

- `mysql`
- `backend`
- `frontend`

其中：

- MySQL 数据保存在 `data/mysql`
- 上传的小说文件保存在 `data/uploads`
- 后端通过业务账号连接 MySQL，不再直接使用 `root`

## 一、准备环境变量

先复制环境变量模板：

```bash
cp .env.example .env
```

然后修改 `.env`：
下面配置可以不用修改，会独立创建一个mysql数据库，前端端口自定义
```env
APP_PORT=9000
MYSQL_ROOT_PASSWORD=your_password
MYSQL_APP_USER=aixs_user
```

参数说明：

- `APP_PORT`：前端对外访问端口
- `MYSQL_ROOT_PASSWORD`：MySQL root 密码，仅数据库初始化和管理使用
- `MYSQL_APP_USER`：项目后端连接数据库使用的业务账号

## 二、首次部署
保证安装了docker compose
在项目根目录执行：

```bash
docker compose up -d --build
```

启动成功后访问：

```text
http://服务器IP:9000/
```

如果你改了 `APP_PORT`，就使用对应端口。

## 三、首次进入系统

项目不再依赖本地大模型配置文件。

首次进入页面时需要：

1. 注册账号
2. 填写密码
3. 选择模型供应商
4. 填写 `Base URL`
5. 填写模型名
6. 填写 `API Key`

系统会先真实调用一次大模型验证配置，验证成功后才会完成注册或保存。

## 四、数据库初始化规则

### 1. 全新部署

如果 `data/mysql` 不存在，MySQL 会在首次启动时自动完成：

- 创建数据库 `MYSQL_DATABASE`
- 创建业务账号 `MYSQL_APP_USER`
- 给业务账号授权访问该数据库

后端启动后会自动创建项目需要的表，例如：

- `users`
- `novels`
- `chapters`
- `dialogue_flows`

### 2. 复用旧数据库目录

如果项目目录里已经存在旧的 `data/mysql`，MySQL 会直接复用旧数据，不会重新初始化用户和权限。

这意味着：

- 你后来再改 `.env` 里的数据库账号密码
- MySQL 不会自动更新旧库里的账号

如果此时出现数据库登录失败，例如：

```text
Access denied for user ...
```

有两种处理方式：

#### 方式 A：重建数据库

如果旧库不需要保留，最简单：

```bash
docker compose down
rm -rf data/mysql
docker compose up -d --build
```

#### 方式 B：保留旧库并手动创建业务账号

如果旧库要保留，就进入 MySQL 手动创建或授权业务账号。

示例 SQL：

```sql
CREATE USER IF NOT EXISTS 'aixs_user'@'%' IDENTIFIED BY '你的业务库密码';
GRANT ALL PRIVILEGES ON aixs.* TO 'aixs_user'@'%';
FLUSH PRIVILEGES;
```

如果数据库名或账号名不是默认值，请替换成你 `.env` 里的值。

## 五、常用命令

### 启动

```bash
docker compose up -d
```

### 重新构建并启动

```bash
docker compose up -d --build
```

### 强制重建后端镜像

当你修改了 Python 依赖、Dockerfile 或后端代码后，建议执行：

```bash
docker compose build --no-cache backend
docker compose up -d
```

### 查看日志

```bash
docker compose logs -f backend
docker compose logs -f frontend
docker compose logs -f mysql
```

### 停止容器

```bash
docker compose down
```

### 连同匿名卷一起停止

```bash
docker compose down -v
```

注意：

- `docker compose down -v` 不会删除 `data/mysql` 这种 bind mount
- 真正要清空数据库数据，仍然需要手动删除 `data/mysql`

## 六、项目数据目录

项目运行后的持久化数据位于：

- `data/mysql`：MySQL 数据
- `data/uploads`：上传的 TXT 小说文件

建议备份这两个目录。

## 七、当前项目使用方式

### 1. 上传小说

- 首页上传 TXT
- 上传成功后进入书籍目录
- 手动点击“拆分章节”

### 2. 解析章节

- 可单章解析
- 可批量选择章节解析
- 已解析过的章节也可以重新解析
- 批量解析时，只会锁定当前解析范围内的章节，其他章节仍可打开

### 3. 解析参考规则

- 当前章只参考上一章已解析结果
- 如果上一章没有解析，则当前章不参考历史结果

### 4. 阅读模式

- 群聊阅读
- 原文阅读

群聊阅读支持：

- 连续滚动阅读
- 点按收消息模式
- 自动加载上下章节
- 保存上次阅读位置

## 八、常见问题排查

### 1. 后端启动失败，提示 Access denied for user

说明后端连接 MySQL 的用户名或密码不对，常见原因：

- `.env` 里的密码和旧库实际账号不一致
- 复用了旧的 `data/mysql`
- 旧库里没有创建 `MYSQL_APP_USER`

优先处理：

```bash
docker compose down
rm -rf data/mysql
docker compose up -d --build
```

如果必须保留旧库，就手动创建业务账号并授权。

### 2. 页面提示“解析中断，请检查后端日志或大模型返回内容”

优先查看后端日志：

```bash
docker compose logs -f backend
```

常见原因：

- API Key 错误
- Base URL 不兼容
- 模型名填写错误
- 服务器无法访问模型接口
- 大模型返回内容格式不合法
- 单章内容太长导致超时

### 3. 修改了代码但 Docker 没生效

执行：

```bash
docker compose build --no-cache backend frontend
docker compose up -d
```

### 4. 新部署后仍然看到旧账号或旧数据

说明你复用了旧的 `data/mysql`。

如果要全新环境：

```bash
docker compose down
rm -rf data/mysql
rm -rf data/uploads
docker compose up -d --build
```

## 九、建议部署顺序

推荐你在服务器上按下面顺序执行：

```bash
cp .env.example .env
vim .env
docker compose up -d --build
docker compose logs -f mysql
docker compose logs -f backend
```

确认：

- `mysql` healthy
- `backend` healthy
- 首页可以打开
- 能正常注册并验证模型配置

之后再开始上传小说和解析章节。
