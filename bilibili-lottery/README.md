Simple lottery app for Bilibili
===

App Process
---
1. load all comments
2. load all danmakus
3. unique all users for comment and danmaku
4. random lucky dog

Technology
---

**protobuf**

> Danmaku API only support protobuf.
>
> Download danmaku proto file from [dm.proto](https://github.com/SocialSisterYi/bilibili-API-collect/blob/master/grpc_api/bilibili/community/service/dm/v1/dm.proto). Check more details at [bilibili-API-collect](https://github.com/SocialSisterYi/bilibili-API-collect/blob/master/danmaku/danmaku_proto.md)
>
> Use `compile-protos.sh` to compile the proto files
