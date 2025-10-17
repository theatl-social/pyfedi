Notes on using Wasabi S3 buckets with Piefed

First, why might you want to use Wasabi S3?

It and Backblaze are the least expensive S3 providers
   - But, Backblaze's S3 implementation is not complete, so probably a poor choice.
   - Wasabi is about half the price of Cloudflare R2 which is significantly less expensive than the others.
   - Wasabi and Cloudflare have an arrangement
     -- If you proxy Wasabi traffic through Cloudflare properly,
        -- egress (and ingress) are free.
        -- Cloudflare will cache the files and provide their CDN services for free
           including serving files from the nearest cached edge.
        -- Using Cloudflare as the Wasabi proxy adds all the Cloudflare security protections.
        -- Both claim 11 9s reliability.
        -- Yes, even the Cloudflare free plan offers this.
   - Cloudflare R2 is probably slightly faster since everything runs inside the much faster Cloudflare network
     while files served by Wasabi go through the Internet to reach Cloudflare.
   - If you use other Cloudflare services, like workers, R2 has better integration and the configuration may be simpler.
   - I have 10 other public facing applications, most using S3 buckets, so I'm going for the money. I use Wasabi.

Proper configuration is necessary.

You must use Cloudflare as your DNS.
You need to use a CNAME as a subdomain entry that points to the wasabi endpoint.
  And that CNAME prepended to your domain name must exactly match the name of the Wasabi bucket.
For the CNAME, you must enable the proxy option.

It's simpler than it sounds. For feddit.online:
I have a CNAME "piefed-media" that points to "s3.wasabisys.com", the Wasabi endpoint for us-east-1. If your bucket
is not in us-east-1, then you would use a different endpoint in the CNAME.

Therefore, my bucket is named "piefed-media.feddit.online". It must be this name.
And images and files will be accessed via the url "https://piefed-media.feddit.online/posts/...."
See, the bucket name and the URL MUST match or no advantages.

Setting up the Wasabi bucket:

You need to create a user and get the access key and the secret key which you will use
in the .ENV file.

By default, all the files written to the bucket will be private. This is not good. Nobody will be able to see
files and pictures in posts. You need to tell Wasabi that all files in the bucket are public. You do this by
going into the bucket settings and selecting the permissions tab. Then you edit the Bucket Policy using this
policy (change the bucket name)

{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowPublicRead",
      "Effect": "Allow",
      "Principal": {
        "AWS": "*"
      },
      "Action": [
        "s3:GetObject",
        "s3:GetObjectVersion"
      ],
      "Resource": "arn:aws:s3:::piefed-media.feddit.online/*"
    }
  ]
}

After you save this policy, the bucket will have public read permissions.

The Piefed .ENV file:

Here is my .ENV file. Note you cannot use "auto" for the region, like in Cloudflare R2. You must specify the proper region.

Note also that S3_ENDPOINT is used by piefed to know where to place the files. It uses the URL, if us-east-1, https://s3.wasabisys.com
to write the files. Files will be read from the bucket using the S3_PUBLIC_URL, as in
https://piefed-media.feddit.online/posts/....

For Wasabi, when proxying through Cloudflare, the S3_BUCKET and the S3_PUBLIC_URL must be the same.

    S3_REGION = 'us-east-1'
    S3_BUCKET = 'piefed-media.feddit.online'
    S3_ENDPOINT = 'https://s3.wasabisys.com'
    S3_PUBLIC_URL = 'piefed-media.feddit.online'
    S3_ACCESS_KEY = 'access key'
    S3_ACCESS_SECRET = 'secret key'
