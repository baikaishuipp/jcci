#### [中文简体](https://github.com/baikaishuipp/jcci/blob/main/README.md) OR [English](https://github.com/baikaishuipp/jcci/blob/main/README.en.md)
# jcci

#### 介绍
Java代码提交影响分析，是一个纯python库，分析Java项目的两次git提交或不同分支代码差异对项目的影响，并生成树形图数据。

PYPI: [jcci](https://pypi.org/project/jcci/) （会落后github几个版本）

#### 软件架构
大致原理同Idea的Find Usage一致，通过代码改动定位代码影响，并不断遍历受影响的类和方法直至找到最上层的controller层

代码主要由python编写，主要涉及2个库：

* javalang java文件语法解析库
* unidiff git diff信息解析库

通过javalang语法解析获取每个Java文件的import class extends implements declarators methods 等信息

通过unidiff 解析git diff信息（diff file, added_line_num, removed_lin_num)

然后根据文件增删的代码行去判断影响了哪些类和方法，不断遍历受影响的类和方法直至找到最上层的controller层

通过传入项目git地址 分支 两次的commit id，即可分析出两次commit id之间代码改动所带来的影响，并生成树图数据方便展示影响链路。

#### 安装教程

##### 方式1：pypi安装（会落后github几个版本）
```
$ pip install jcci
```

##### 方式2：克隆项目（推荐此种方式）
```
$ git clone https://github.com/baikaishuipp/jcci.git
```

#### 使用说明

##### 方式1：pypi安装（会落后github几个版本）
新建python项目，新建python文件，代码如下：
```
from jcci import jcci

# 同一分支不同commit比较
jcci.analyze('git@xxxx.git','master','commit_id1','commit_id2', 'username1')

```

##### 方式2：克隆项目（推荐此种方式）
项目克隆下来后，新建python文件，引入jcci项目src目录下的jcci
```
from path.to.jcci.src.jcci import jcci

# 同一分支不同commit比较
jcci.analyze('git@xxxx.git','master','commit_id1','commit_id2', 'username1')

```
###### 参数说明：
* project_git_url - 项目git地址，代码使用本机git配置clone代码，确保本机git权限或通过用户名密码/token的方式拼接url来clone代码。示例：https://userName:password@github.com/xxx.git 或 https://token@github.com/xxx.git
* username1 - 随便输入，为了避免并发分析同一项目导致结果错误，用户1分析项目A时，用户B需要等待，所以设置了该参数

运行时，会将项目克隆到目录中，然后进行分析，生成后缀格式为commit_id1...commit_id2.cci的文件，其中包含分析结果生成的树形图数据，下载[jcci-result.html](https://github.com/baikaishuipp/jcci/blob/main/jcci-result.html) ，选择分析结果的.cci文件，即可可通过视图显示。

##### CCI result
![result](./images/cci-result.png)

##### CCI result tree view
![treeView](./images/cii-result-tree.png)

#### 参与贡献

1.  Fork 本仓库
2.  新建 Feat_xxx 分支
3.  提交代码
4.  新建 Pull Request

#### 开源不易，如本工具对您有帮助，请点一下右上角 star ⭐ , 谢谢~~~

#### 沟通交流
扫码加微信，备注：JCCI微信群交流

![微信交流群](./images/wechat.jpg) 
