-- Disable PayTabs payment provider
UPDATE payment_provider
   SET paytabs_profile_id = NULL,
       paytabs_server_key = NULL
 WHERE code = 'paytabs';
