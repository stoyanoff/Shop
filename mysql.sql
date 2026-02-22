SET NAMES utf8;
SET time_zone = '+00:00';
SET foreign_key_checks = 0;
SET sql_mode = 'NO_AUTO_VALUE_ON_ZERO';

SET NAMES utf8mb4;

DROP DATABASE IF EXISTS `shop`;
CREATE DATABASE `shop` /*!40100 DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci */;
USE `shop`;

DROP TABLE IF EXISTS `categories`;
CREATE TABLE `categories` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `name` varchar(100) NOT NULL,
  `slug` varchar(100) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `slug` (`slug`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

INSERT INTO `categories` (`id`, `name`, `slug`) VALUES
(1,	'Семена',	'seeds'),
(2,	'Стайни растения',	'roomplants'),
(3,	'Дворни растения',	'outdoorplants'),
(4,	'Агроаптека',	'agropharmacy'),
(5,	'Букети',	'bouquet');

DROP TABLE IF EXISTS `services`;
CREATE TABLE `services` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `name` varchar(100) NOT NULL,
  `slug` varchar(100) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `slug` (`slug`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

INSERT INTO `services` (`id`, `name`, `slug`) VALUES
(1,	'Букет по поръчка',	'custombouquet');

DROP TABLE IF EXISTS `products`;
CREATE TABLE `products` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `name` varchar(100) NOT NULL,
  `description` text DEFAULT NULL,
  `price` decimal(10,2) NOT NULL,
  `stock` int(11) DEFAULT 0,
  `image` varchar(255) DEFAULT NULL,
  `category_id` int(11) DEFAULT NULL,
  `service_id` int(11) DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `category_id` (`category_id`),
  KEY `service_id` (`service_id`),
  CONSTRAINT `products_ibfk_1` FOREIGN KEY (`category_id`) REFERENCES `categories` (`id`),
  CONSTRAINT `products_ibfk_2` FOREIGN KEY (`service_id`) REFERENCES `services` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

INSERT INTO `products` (`id`, `name`, `description`, `price`, `stock`, `image`, `category_id`, `service_id`) VALUES
(1,	'Домати семена',	'Семена за домати сорт Рио Гранде',	3.50,	100,	'tomato.jpg',	1,	NULL),
(2,	'Тор NPK',	'Комплексен тор NPK 15:15:15',	25.00,	50,	'fertilizer.jpg',	4,	NULL),
(3,	'Букет червени рози',	'Красив букет от червени рози',	20.00,	10,	'https://larose.bg/frontstore/images/products/buket-ot-21-cherveni-rozi-pic-4_thickbox_default.jpg',	5,	NULL);

DROP TABLE IF EXISTS `users`;
CREATE TABLE `users` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `username` varchar(50) NOT NULL,
  `password_hash` varchar(255) NOT NULL,
  `role` enum('customer','admin') DEFAULT 'customer',
  `realname` varchar(100) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `username` (`username`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

INSERT INTO `users` (`id`, `username`, `password_hash`, `role`, `realname`) VALUES
(1,	'admin',	'scrypt:32768:8:1$ZZhFNehCmQUwzKUc$0aa04887bc6f083179a113c6c96c1b88ae042f8a25c886aa86ac939ad1d8885bd05bd87c71a19fbc166ad11d335998f53563dab610c16407cbeb24fce48f42f1',	'admin',	'Таня Стоянова'),
(2,	'user1',	'scrypt:32768:8:1$tYUuytlvSZzwFwj2$be41e9c9b495ac9a4c3b7fcbcbb8a6b5c7860daf77ad325764b37a74479a0df2040e2e969f770db4b3966fd1b48e61f17557158578c8830f233a7f4b409ebdc4',	'customer',	'Потребител');

DROP TABLE IF EXISTS `orders`;
CREATE TABLE `orders` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `user_id` int(11) DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT current_timestamp(),
  `status` enum('pending','completed','canceled') DEFAULT 'pending',
  PRIMARY KEY (`id`),
  KEY `user_id` (`user_id`),
  CONSTRAINT `orders_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

DROP TABLE IF EXISTS `order_items`;
CREATE TABLE `order_items` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `order_id` int(11) DEFAULT NULL,
  `product_id` int(11) DEFAULT NULL,
  `quantity` int(11) NOT NULL,
  `price` decimal(10,2) NOT NULL,
  PRIMARY KEY (`id`),
  KEY `order_id` (`order_id`),
  KEY `product_id` (`product_id`),
  CONSTRAINT `order_items_ibfk_1` FOREIGN KEY (`order_id`) REFERENCES `orders` (`id`),
  CONSTRAINT `order_items_ibfk_2` FOREIGN KEY (`product_id`) REFERENCES `products` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

DROP TABLE IF EXISTS `delivery`;
CREATE TABLE `delivery` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `user_id` int(11) DEFAULT NULL,
  `address_line1` varchar(255) NOT NULL,
  `address_line2` varchar(255) DEFAULT NULL,
  `city` varchar(100) NOT NULL,
  `state` varchar(100) DEFAULT NULL,
  `postal_code` varchar(20) DEFAULT NULL,
  `country` varchar(100) NOT NULL,
  `is_default` tinyint(1) DEFAULT 0,
  PRIMARY KEY (`id`),
  KEY `user_id` (`user_id`),
  CONSTRAINT `delivery_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

INSERT INTO `delivery` (`id`, `user_id`, `address_line1`, `address_line2`, `city`, `state`, `postal_code`, `country`, `is_default`) VALUES
(1,	1,	'на центъра',	NULL,	'Победа',	'Плевен',	'5873',	'България',	1);

DELIMITER //
CREATE PROCEDURE SetDefaultDeliveryAddress(IN p_user_id INT, IN p_address_id INT)
BEGIN
    -- First, set all addresses for this user to not default
    UPDATE delivery SET is_default = FALSE WHERE user_id = p_user_id;
    -- Then set the specified address as default
    UPDATE delivery SET is_default = TRUE WHERE id = p_address_id AND user_id = p_user_id;
END //
DELIMITER ;

