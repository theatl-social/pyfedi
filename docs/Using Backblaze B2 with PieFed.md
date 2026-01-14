# Overview
- [Step 1: Create a new public Bucket in Backblaze](#step_1)
- [Step 2: Get the Friendly Name for your Bucket](#step_2)
- [Step 3: Add a CNAME record pointing to the friendly name for your bucket](#step_3)
- [Step 4: Set rewrite rules in your DNS](#step_4)
- [Step 5: Get your access credentials](#step_5)
- [Step 6: Add S3 environment variables to PieFed](#step_6)

<a id="step_1"></a>

## Step 1: Create a new public Bucket in Backblaze

1. From the Buckets overview page, click **Create a Bucket**

![Create a new Bucket button](backblaze_b2_process_images/create_bucket_button.png)

2. Give the Bucket a unique name

![Bucket Unique Name](backblaze_b2_process_images/unique_name.png)

3. Set the Bucket to **Public**

![Files in Bucket are Public](backblaze_b2_process_images/public_bucket.png)

4. Click **Create a Bucket**

![Create a Bucket button from new Bucket overview](backblaze_b2_process_images/create_bucket.png)

<a id="step_2"></a>

## Step 2: Get the Friendly Name for your Bucket

1. From the Buckets overview page, find your new bucket, and click **Upload/Download**

![Upload/Download button](backblaze_b2_process_images/upload_to_bucket.png)

2. Drop or select a file (any file will work, but don't put anything private in this Bucket)

![Drop or select a file](backblaze_b2_process_images/drop_files.png)
![Upload success](backblaze_b2_process_images/upload_success.png)

3. Click on the file you uploaded

![File overview](backblaze_b2_process_images/upload_overview.png)

4. Copy the part of the Friendly URL between the `https://` and the next `/`. In this case, that's `f004.backblazeb2.com`

<a id="step_3"></a>

## Step 3: Add a CNAME record pointing to the friendly name for your bucket

In your DNS (we're using Cloudflare in our example), add a new CNAME record with these details:
- **Name:** Whatever prefix you want to use for your media. We'll use `piefed-media`
- **Target:** The part of the Friendly URL you copied. In this case, that's `f004.backblazeb2.com`
- **Proxy status:** Enabled (orange)

![CNAME record details](backblaze_b2_process_images/cloudflare_cname.png)

<a id="step_4"></a>

## Step 4: Set rewrite rules in your DNS

We're using Cloudflare in our example. If you are using a different DNS provider, check their documentation.

1. From the left-side menu, click on **Overview** under **Rules**

![Overview in left-side menu](backblaze_b2_process_images/rules_overview.png)

2. Click **Create rule**

![Create rule button](backblaze_b2_process_images/create_rule.png)

3. Give your rule a name. We'll use `piefed media`

![Rule name](backblaze_b2_process_images/name_rule.png)

4. Under **If incoming requests match...**, choose **Custom filter expression**

![Custom filter expression](backblaze_b2_process_images/custom_filter_expression.png)

5. Under **When incoming requests match...**, set these values:
- **Field:** Hostname
- **Operator:** equals
- **Value:** The media CNAME you set up above. In our case that's `piefed-media.your.domain.here`

![Incoming request match](backblaze_b2_process_images/match.png)

6. Under **Then...**, set these values:
- **Path:** Rewrite to...
    - Dynamic
    - `concat("/file/your-super-unique-bucket-name", http.request.uri.path)` (replace `your-super-unique-bucket-name` with the name of your Bucket)
- **Query:** Preserve

![Rewrite parameters](backblaze_b2_process_images/then_rewrite.png)

7. Click **Save**

![Save rule button](backblaze_b2_process_images/save_rule.png)

<a id="step_5"></a>

## Step 5: Get your access credentials

1. Head back to your Backblaze dashboard
2. Click **Application Keys** from the left-side menu

![Application Keys](backblaze_b2_process_images/application_keys.png)

3. Click **Add a New Application Key**

![Add a New Application Key button](backblaze_b2_process_images/add_key_button.png)

4. Enter these details:
- **Name of Key:** A name for your key. We'll use piefed-media
- **Allow access to Bucket(s):** Your new Bucket
- **Type of Access:** Read and Write
- **Allow List All Bucket Names:** Leave unchecked
- **File name prefix:** Leave blank
- **Duration:** Leave blank

![Add Application Key](backblaze_b2_process_images/add_key.png)

5. Click **Create New Key**

6. Take note of your **keyID** and **applicationKey**

![Key details](backblaze_b2_process_images/key_details.png)

<a id="step_6"></a>

## Step 6: Add S3 environment variables to PieFed

1. Head back to your Backblaze dashboard and find these:
- **S3_BUCKET:** The name of your Bucket
- **S3_ENDPOINT:** The **Endpoint**
- **S3_REGION:** The part of the **Endpoint** between `s3.` and `.backblazeb2`

![Bucket overview](backblaze_b2_process_images/bucket_overview.png)

2. Add these values to your environment variables file (.env if you did the [manual install](https://codeberg.org/rimu/pyfedi/src/branch/main/INSTALL.md#setup-env-file), or .env.docker if you did the [docker install](https://codeberg.org/rimu/pyfedi/src/branch/main/INSTALL-docker.md#prepare-docker-environment-file)):

| **Key**              | **Value**                                                                            |
|----------------------|--------------------------------------------------------------------------------------|
| **S3_BUCKET**        | The name of your Bucket                                                              |
| **S3_ENDPOINT**      | The **Endpoint**                                                                     |
| **S3_REGION**        | The part of the **Endpoint** between `s3.` and `.backblazeb2`                        |
| **S3_PUBLIC_URL**    | The media CNAME you set up above. In our case that's `piefed-media.your.domain.here` |
| **S3_ACCESS_KEY**    | Your **keyID**                                                                       |
| **S3_ACCESS_SECRET** | Your **applicationKey**                                                              |


These are the values from our example:

```
S3_BUCKET = 'your-super-unique-bucket-name'
S3_ENDPOINT = 'https://s3.us-west-004.backblazeb2.com'
S3_REGION = 'us-west-004'
S3_PUBLIC_URL = 'piefed-media.your.domain.here'
S3_ACCESS_KEY = '004819c3ba9b31b0000000003'
S3_ACCESS_SECRET = 'K004Uei/7Vf90FzWuN3zoGl5npK3zZc'
```
That's it! Restart your instance and check Backblaze to make sure files are showing up in your Bucket.
