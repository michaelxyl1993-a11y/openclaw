# Product Intel v1.20 Feishu Multi-attachment Download Dry Run

## 结论

- 本次未调用真实飞书 API。
- 本次未下载真实附件。
- ready_for_real_download：true
- ready_for_multi_file_batch_runner：true
- 附件总数：5
- 支持附件：4
- 不支持附件：1

## 可进入批处理的文件

- product_intel/feishu_downloads/mock_echotik_products.xlsx
- product_intel/feishu_downloads/mock_fastmoss_products.xlsx
- product_intel/feishu_downloads/mock_kalodata_products.xlsx
- product_intel/feishu_downloads/mock_manual_products.xlsx

## 不支持或异常附件

- readme.pdf：不支持的文件类型，仅允许 .csv / .xlsx / .xls

## 下一步

`python3 -m product_intel.multi_file_batch_runner --inputs product_intel/feishu_downloads/mock_echotik_products.xlsx product_intel/feishu_downloads/mock_fastmoss_products.xlsx product_intel/feishu_downloads/mock_kalodata_products.xlsx product_intel/feishu_downloads/mock_manual_products.xlsx --source auto --market de --output-dir product_intel/output_multi_file_from_feishu`
