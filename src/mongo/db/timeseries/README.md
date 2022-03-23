# Time-Series Collections


MongoDB supports a new collection type for storing time-series data with the [timeseries](../commands/create.idl)
collection option. A time-series collection presents a simple interface for inserting and querying
measurements while organizing the actual data in buckets.

MongoDB 在5.0中支持了新的`timeseries collection`类型的选项，该类型用于存储时序型数据。`timeseries collection`提供了一组用于插入和查询测量值的简单接口，同时底层实际的数据是存储在以`bucket`形式的集合中。

A minimally configured time-series collection is defined by providing the [timeField](timeseries.idl)
at creation. Optionally, a meta-data field may also be specified to help group
 measurements in the buckets. MongoDB also supports an expiration mechanism on measurements through
the `expireAfterSeconds` option.

在创建`timeseries collection`时，`timeField`字段是最小必备的配置项。`metaField`是另一个可选的、可被指定的元数据字段，它是用于在`bucket`中对测量值分组的依据。MongoDB通过提供`expireAfterSeconds`字段选项，也支持了对测量值的过期机制。

A time-series collection `mytscoll` in the `mydb` database is represented in the [catalog](../catalog/README.md) by a
combination of a view and a system collection:

在`mydb`数据库中有个以`mytscoll` 命名的`timeseries collection`，该集合在MongoDB内部的`catelog`(用于存储集合或视图的信息)里是由一个视图和一个系统集合组成的。

- 
* The view `mydb.mytscoll` is defined with the bucket collection as the source collection with
certain properties:
    * Writes (inserts only) are allowed on the view. Every document inserted must contain a time field.
    * Querying the view implicitly unwinds the data in the underlying bucket collection to return
      documents in their original non-bucketed form.
        * The aggregation stage [$_internalUnpackBucket](../pipeline/document_source_internal_unpack_bucket.h) is used to
          unwind the bucket data for the view.
* The system collection has the namespace `mydb.system.buckets.mytscoll` and is where the actual
  data is stored.
    * Each document in the bucket collection represents a set of time-series data within a period of time.
    * If a meta-data field is defined at creation time, this will be used to organize the buckets so that
      all measurements within a bucket have a common meta-data value.
    * Besides the time range, buckets are also constrained by the total number and size of measurements.

- `mydb.mytscoll` 是个视图，它在MongoDB底层是用`bucket collection`作为包含特定属性的原始集合实现的：
  - 该视图是可写的（仅支持插入）。同时每个被插入的文档必须包含时间字段。
  - 在查询视图时，它会隐式地展开底层在`bucket collection`中存储的数据，然后返回原始的非`bucket`形式的文档数据。
    - 该视图就是通过`aggregation`里的`$_internalUnpackBucket`来实现展开`bucket`里数据的。
- 该系统集合的命名空间是`mydb.system.buckets.mytscoll`，它是用来存储实际数据的。
  - 每一个在`bucket collection`里的文档，都表示了一组区间间隔的时序型数据。
  - 如果在创建`timeseries collection`时，定义了`metaField`元数据字段，那么所有在`bucket`里的测量值都会有这个通用的元数据字段。
  - 除了时间范围，`bucket`还限制了每个文档数据的总条数以及测量值的大小。



## Bucket Collection Schema

```
{
    _id: <Object ID with time component equal to control.min.<time field>>,
    control: {
        // <Some statistics on the measurements such min/max values of data fields>
        version: 1,  // Version of bucket schema. Currently fixed at 1 since this is the
                     // first iteration of time-series collections.
        min: {
            <time field>: <time of first measurement in this bucket, rounded down based on granularity>,
            <field0>: <minimum value of 'field0' across all measurements>,
            <field1>: <maximum value of 'field1' across all measurements>,
            ...
        },
        max: {
            <time field>: <time of last measurement in this bucket>,
            <field0>: <maximum value of 'field0' across all measurements>,
            <field1>: <maximum value of 'field1' across all measurements>,
            ...
        },
        closed: <bool> // Optional, signals the database that this document will not receive any
                       // additional measurements.
    },
    meta: <meta-data field (if specified at creation) value common to all measurements in this bucket>,
    data: {
        <time field>: {
            '0', <time of first measurement>,
            '1', <time of second measurement>,
            ...
            '<n-1>': <time of n-th measurement>,
        },
        <field0>: {
            '0', <value of 'field0' in first measurement>,
            '1', <value of 'field0' in first measurement>,
            ...
        },
        <field1>: {
            '0', <value of 'field1' in first measurement>,
            '1', <value of 'field1' in first measurement>,
            ...
        },
        ...
    }
}
```

## Indexes索引

In order to support queries on the time-series collection that could benefit from indexed access
rather than collection scans, indexes may be created on the time, meta-data, and meta-data subfields
of a time-series collection. Starting in v5.2, indexes on time-series collection measurement fields
are permitted. The index key specification provided by the user via `createIndex` will be converted
to the underlying buckets collection's schema.
* The details for mapping the index specification between the time-series collection and the
  underlying buckets collection may be found in
  [timeseries_index_schema_conversion_functions.h](timeseries_index_schema_conversion_functions.h).
* Newly supported index types in v5.2 and up
  [store the original user index definition](https://github.com/mongodb/mongo/blob/cf80c11bc5308d9b889ed61c1a3eeb821839df56/src/mongo/db/timeseries/timeseries_commands_conversion_helper.cpp#L140-L147)
  on the transformed index definition. When mapping the bucket collection index to the time-series
  collection index, the original user index definition is returned.

为了保证`timeseries collection`的查询可以受益于索引扫描而不是全表扫描，`timeseries collection`允许索引可以被创建在时间上，元数据上以及元数据的子属性上。从MongoDB5.2开始，在`timeseries collection`也允许索引被创建在测量值上。用户使用`createIndex`命令提供的索引规范被转换为底层`buckets collection`的模式。
- `timeseries collection`与底层的`buckets collection`之间的索引映射转换关系细节，你可以参考[timeseries_index_schema_conversion_functions.h](https://github.com/mongodb/mongo/blob/master/src/mongo/db/timeseries/timeseries_index_schema_conversion_functions.h).
- 在v5.2及以上版本的最新支持的索引类型，`timeseries collection`会存储用户原始的索引定义到变换后的索引定义上。当从底层的`bucket collection`的索引映射到`timeseries collections`的索引时，会返回用户原始的索引定义。

Once the indexes have been created, they can be inspected through the `listIndexes` command or the
`$indexStats` aggregation stage. `listIndexes` and `$indexStats` against a time-series collection
will internally convert the underlying buckets collections' indexes and return time-series schema
indexes. For example, a `{meta: 1}` index on the underlying buckets collection will appear as
`{mm: 1}` when we run `listIndexes` on a time-series collection defined with `mm` for the meta-data
field.

当索引被创建后，可以通过`listIndexes`命令或`$indexStats`聚合计划来检查。`listIndexes` 和`$indexStats`是作用于`timeseries collections`的，执行时，它们会在内部将底层的`bucket collection`的索引转化成`timeseries`格式的索引，并返回。比如，当我们在元数据字段中定义有`mm`的`timeseries collection`上执行`listIndexes`命令时，底层的`bucket collection`的`{meta:1}`索引，将会以`{mm:1}`格式返回。

`dropIndex` and `collMod` (`hidden: <bool>`, `expireAfterSeconds: <num>`) are also supported on
time-series collections.

Supported index types on the time field:
* [Single](https://docs.mongodb.com/manual/core/index-single/).
* [Compound](https://docs.mongodb.com/manual/core/index-compound/).
* [Hashed](https://docs.mongodb.com/manual/core/index-hashed/).
* [Wildcard](https://docs.mongodb.com/manual/core/index-wildcard/).
* [Sparse](https://docs.mongodb.com/manual/core/index-sparse/).
* [Multikey](https://docs.mongodb.com/manual/core/index-multikey/).
* [Indexes with collations](https://docs.mongodb.com/manual/indexes/#indexes-and-collation).

时间字段上支持的索引类型：

- [单字段索引](https://docs.mongodb.com/manual/core/index-single/)
- [组合索引](https://docs.mongodb.com/manual/core/index-compound/)
- [哈希索引](https://docs.mongodb.com/manual/core/index-hashed/)
- [通配符索引](https://docs.mongodb.com/manual/core/index-wildcard/)
- [稀疏索引](https://docs.mongodb.com/manual/core/index-sparse/)
- [多键索引](https://docs.mongodb.com/manual/core/index-multikey/)
- [带排序的索引](https://docs.mongodb.com/manual/indexes/#indexes-and-collation).


Supported index types on the meta-data field and meta-data subfields:
* All of the supported index types on the time field.
* [2d](https://docs.mongodb.com/manual/core/2d/) in v5.2 and up.
* [2dsphere](https://docs.mongodb.com/manual/core/2dsphere/) in v5.2 and up.
* [Partial](https://docs.mongodb.com/manual/core/index-partial/) in v5.2 and up.

元数据字段和元数据子字段支持的索引类型：

- 支持所有时间字段上支持的索引类型
- v5.2及以上版本支持[2d]((https://docs.mongodb.com/manual/core/2d/)) 索引
- v5.2及以上版本支持[2dsphere]((https://docs.mongodb.com/manual/core/2dsphere/)) 索引
- v5.2及以上版本支持 [Partial索引](https://docs.mongodb.com/manual/core/index-partial/) in v5.2 and up.


Supported index types on measurement fields in v5.2 and up only:
* [Single](https://docs.mongodb.com/manual/core/index-single/).
* [Compound](https://docs.mongodb.com/manual/core/index-compound/).
* [2dsphere](https://docs.mongodb.com/manual/core/2dsphere/).
* [Partial](https://docs.mongodb.com/manual/core/index-partial/).

仅在v5.2及以上版本，测量值字段支持的索引类型

- [单字段索引](https://docs.mongodb.com/manual/core/index-single/)
- [组合索引](https://docs.mongodb.com/manual/core/index-compound/)
- [2dsphere](https://docs.mongodb.com/manual/core/2dsphere/)
- [部分条件索引](https://docs.mongodb.com/manual/core/index-partial/)

Index types that are not supported on time-series collections include
[unique](https://docs.mongodb.com/manual/core/index-unique/), and
[text](https://docs.mongodb.com/manual/core/index-text/).
`timeseries collections 上不支持的索引类型，包括 [唯一索引](](https://docs.mongodb.com/manual/core/index-unique/))以及[文本索引](https://docs.mongodb.com/manual/core/index-text/)

## BucketCatalog

In order to facilitate efficient bucketing, we maintain the set of open buckets in the
`BucketCatalog` found in [bucket_catalog.h](bucket_catalog.h). At a high level, we attempt to group
writes from concurrent writers into batches which can be committed together to minimize the number
of underlying document writes. A writer will insert each document in its input batch to the
`BucketCatalog`, which will return a handle to a `BucketCatalog::WriteBatch`. Upon finishing its
inserts, the writer will check each write batch. If no other writer has already claimed commit
rights to a batch, it will claim the rights and commit the batch itself; otherwise, it will set the
batch aside to wait on later. When it has checked all batches, the writer will wait on each
remaining batch to be committed by another writer.

为了保证高效地桶（分组）操作，我们在`BucketCatalog`里维护了一组开启的桶，你可以在[bucket_catalog.h](https://github.com/mongodb/mongo/blob/master/src/mongo/db/timeseries/bucket_catalog.h)找到。在更高的级别，我们尝试着把并发写程序的写操作分组合并为可以一起提交地批处理，以减少对底层文档的写次数。写程序会插入它的输入批处理里的每一个文档到`BucketCatalog`，然后`BucketCatalog`会返回一个`BucketCatalog::WriteBatch`的处理器。一旦完成上面那些插入操作后，写程序就会检查每个写批处理。如果没有其他的写程序已经对批处理声明提交的权利，那么它会声明权利，并会提交它的批处理。否则，写程序将会稍后再提交处理。当它检查完所有的批处理，写程序将会等待其他的写程序提交每个剩下的批处理。

Internally, the `BucketCatalog` maintains a list of updates to each bucket document. When a batch
is committed, it will pivot the insertions into the column-format for the buckets as well as
determine any updates necessary for the `control` fields (e.g. `control.min` and `control.max`).

在内部，`BucketCatalog`维护一组对每个`bucket` 文档的更新操作。当批处理被提交时，它会将这些插入转换到成`buckets`的列格式，并确保任何`control`字段的更新（例如`control.min` 和 `control.max`）

Any time a bucket document is updated without going through the `BucketCatalog`, the writer needs
to call `BucketCatalog::clear` for the document or namespace in question so that it can update its
internal state and avoid writing any data which may corrupt the bucket format. This is typically
handled by an op observer, but may be necessary to call from other places.

当`bucket`文档在没有通过`BucketCatalog`的情况下被更新时，写程序就需要为有问题的文档或命名空间去调用`BucketCatalog::clear` ，这样它就可以更新它的内部状态，避免写入任何可能破坏`bucket `格式的数据。这通常由OP观察者处理，但可能需要通过其他地方去调用。

A bucket is closed either manually, by setting the optional `control.closed` flag, or automatically
by the `BucketCatalog` in a number of situations. If the `BucketCatalog` is using more memory than
it's given threshold (controlled by the server parameter
`timeseriesIdleBucketExpiryMemoryUsageThreshold`), it will start to close idle buckets. A bucket is
considered idle if it is open and it does not have any uncommitted measurements pending. The
`BucketCatalog` will also close a bucket if it contains more than the maximum number of measurements
(`timeseriesBucketMaxCount`), if it contains more than the maximum amount of data
(`timeseriesBucketMaxSize`), or if a new measurement would cause the bucket to span a greater
amount of time between it's oldest and newest time stamp than is allowed (currently hard-coded to
one hour). If an incoming measurement is schematically incompatible relative to the measurements 
which have already landed in a given bucket, that bucket will be closed and is tracked with the
`numBucketsClosedDueToSchemaChange` metric.

`bucket`既可以通过手动设置选项`control.closed` 标识来关闭，也可以在许多场景下通过 `BucketCatalog` 自动关闭。如果`BucketCatalog`使用了超出给定的阈值（可通过服务器参数`timeseriesIdleBucketExpiryMemoryUsageThreshold`控制）的更多内存，此时它将会开始去关闭空闲的`bucket`。如果`bucket`是开启的且它没有任何未处于等待中未提交的测量值时，那么它就会被视为空闲的`bucket`。在下面这些场景下 `BucketCatalog` 也会关闭`bucket`: 如果它拥有超过最大阈值（`timeseriesBucketMaxCount`）的测量值数据的数量；如果它拥有过大的数据量大小（`timeseriesBucketMaxSize`）；又或者一个新的测量值数据是否是会导致`bucket`在其最旧的时间戳和最新的时间戳之间跨度比允许的间隔更长的时间（当前硬编码为一小时）。如果传入的测量值在原理上与已经到达给定`bucket`的度量不兼容，该`bucket`将被关闭，同时可以使用`numBucketsClosedDueToSchemaChange`度量进行跟踪。  

The first time a write batch is committed for a given bucket, the newly-formed document is
inserted. On subsequent batch commits, we perform an update operation. Instead of generating the
full document (a so-called "classic" update), we create a DocDiff directly (a "delta" or "v2"
update).

在第一次提交给定`bucket`的写批处理时，就会生成新的完整的文档。后续的批处理提交中，我们只执行更新操作，不再生成新的完整的文档（因此称为‘经典’更新），是直接创建`DocDiff `（“delta”或者v2的更新）

# Granularity粒度（时间间隔单位）

The `granularity` option for a time-series collection can be set at creation to be 'seconds',
'minutes' or 'hours'. A later `collMod` operation can change the option from 'seconds' to 'minutes'
or from 'minutes' to 'hours', but no other transitions are currently allowed. This parameter is
intended to convey the rough time period between measurements in a given time-series, and is used to
tweak other internal parameters that affect bucketing.

`timeseries collection`的`granularity` 选项在集合创建的时候，可以被设置成`seconds`，`minutes`或者`hours`。后期可通过`colMod`操作来修改这个选项从`seconds`到`minutes`或者从`minutes`到`hours`，除此之外的转化修改目前都是不支持的。该参数想要表示在已给定的时序型测量数据之间的粗略的时间间隔，同时也用于调节其他内部参数对分组的影响。

The maximum span of time that a single bucket is allowed to cover is controlled by `granularity`,
with the maximum span being set to one hour for 'seconds', 24 hours for 'minutes', and 30 days
for 'hours'.

单个`bucket`被允许的最大时间跨度，是由`granularity`选项控制，对于`seconds`，最大的时间跨度被设置成1小时，对于`minutes`就是24小时，对于`hours`就是30天。

When a new bucket is opened by the `BucketCatalog`, the timestamp component of its `_id`, and
equivalently the value of its `control.min.<time field>`, will be taken from the first measurement
inserted to the bucket and rounded down based on the `granularity`. It will be rounded down to the
nearest minute for 'seconds', the nearest hour for 'minutes', and the nearest day for 'hours'. This
rounding may not be perfect in the case of leap seconds and other irregularities in the calendar,
and will generally be accomplished by basic modulus aritmetic operating on the number of seconds
since the epoch, assuming 60 seconds per minute, 60 minutes per hour, and 24 hours per day.

 当通过`BucketCatalog`开启新的`bucket`时，`_id`里的时间戳就是等同于`control.min.<time field>`的值，该值是从第一个插入bucket的测量数据中根据`granularity`选项来向下近似舍入而得到的。对于`seconds`，它将向下舍入到最接近的分钟，对于`minutes`，将向下舍入到最接近的小时，对于`hours`，它将向下舍入到最接近的日期。在闰秒和日历中的其他不规则情况下，这种舍入可能并不完美，并且通常通过对自纪元以来的秒数进行基本模运算来完成，假设每分钟 60 秒，每小时 60 分钟，以及每天 24 小时。
 
# Updates and Deletes

Time-series collections support deletes which satisfy the following restrictions:
* Query on only the `metaField`
* `multi: true`

and updates which satisfy these same conditions, plus the following:
* Update only the `metaField`
* Update specified as an update document (versus a replacement document or update pipeline)
* `upsert: false`

 `timeseries collection` 支持符合以下限制的删除语句

- 仅支持`metaField`的属性的查询语句
- 支持批量操作

同时更新满足上面同样的条件，另外遵循：

- 仅支持`metaField`对应的属性值
- 更新操作指定一个带有更新运算符表达式的更新文档（而不是替换文档或者更新的pipeline操作）
- 不支持`upsert:true ` 操作
 
 
These updates and deletes are performed by translating the operation into a corresponding update or
delete on the underlying buckets collection. In particular, for both the query and update document,
we replace any references to the collection's `metaField` with literal `"meta"` (see
[Bucket Collection Schema](#bucket-collection-schema)).

 这些更新与删除的执行都会被转换成相对应的底层的`bucket collection`的更新或删除操作。特别是，对于查询和更新文档，我们会使用真正的字段`meta` 替换集合的`metaField`。（参见 [Bucket 集合规范](https://github.com/mongodb/mongo/blob/master/src/mongo/db/timeseries/README.md#bucket-collection-schema)）
 
For example, for a time-series collection `db.ts` created with `metaField: "tag"`, consider an
update on this collection with query `{"tag.tag.a": "a"}` and update document
`{$set: {"tag.tag.a": "A"}, $rename: {"tag.tag.b": "tag.tag.c"}}`. This gets translated into an
update on `db.system.buckets.ts` with query `{"meta.tag.a": "a"}` and update document
`{$set: {"meta.tag.a": "A"}, $rename: {"meta.tag.b": "meta.tag.c"}}`. We can then execute this
translated update as a regular update operation. The same process applies for deletes.

 例如，对于一个使用 `metaField: "tag"`创建的`timeseries`集合`db.ts`，考虑一个对这个集合的更新操作，其查询语句是`{"tag.tag.a": "a"}` ，同时更新文档语句是 `{$set: {"tag.tag.a": "A"}, $rename: {"tag.tag.b": "tag.tag.c"}}`。这个更新操作在 `db.system.buckets.ts`上会被转换成，查询语句是`{"meta.tag.a": "a"}`，更新语句是 `{$set: {"meta.tag.a": "A"}, $rename: {"meta.tag.b": "meta.tag.c"}}`。然后这个转换后的更新语句就可以像普通的更新操作一样执行。上面这些转换流程也适用于删除操作。
 
# References参考文献
See:
[MongoDB Blog: Time Series Data and MongoDB: Part 2 - Schema Design Best Practices](https://www.mongodb.com/blog/post/time-series-data-and-mongodb-part-2-schema-design-best-practices)

# Glossary词汇表
**bucket**: A group of measurements with the same meta-data over a limited period of time.

**bucket collection**: A system collection used for storing the buckets underlying a time-series
collection. Replication, sharding and indexing are all done at the level of buckets in the bucket
collection.

**measurement**: A set of related key-value pairs at a specific time.

**meta-data**: The key-value pairs of a time-series that rarely change over time and serve to
identify the time-series as a whole.

**time-series**: A sequence of measurements over a period of time.

**time-series collection**: A collection type representing a writable non-materialized view that
allows storing and querying a number of time-series, each with different meta-data.

 **bucket**：带有相同的元数据且在一段有限制的间隔区间内的测量值组。

**bucket collection** ： 用于存储时序型集合的底层的分组桶的系统集合。复制、分片和索引都是在桶级别上完成的。  

**measurement**：带有特定时间序列的K-V集合。

**meta-data**：时序序列里很少随时间变化的K-V对，同时可以用于识别整个时序序列。

**time-series**：一段间隔内的一系列测量值。  

**time-series collection**：一种表示可写的非物化的视图的集合类型，它允许存储和查询多个时间序列，每个序列可以有不同的元数据。
 
