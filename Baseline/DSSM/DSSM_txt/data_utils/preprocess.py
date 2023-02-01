import numpy as np
import pandas as pd
import torch


def get_df(texts_path):  # load zh_en title as pd.DataFrame
    news_df = pd.read_csv(texts_path, low_memory=False, iterator=True, encoding='utf-8', usecols=[0, 1, 2], header=None)
    loop = True
    chunkSize = 10000
    chunks = []
    while loop:
        try:
            chunk = news_df.get_chunk(chunkSize)
            chunks.append(chunk)
        except StopIteration:
            loop = False
            # print("news_df is loaded.")
    news_df = pd.concat(chunks, ignore_index=True)
    news_df.columns = ['video_id', 'title', 'title_en']
    return news_df


def read_text(texts_path, which_language):
    item_id_to_dic = {}
    item_name_to_id = {}
    item_id = 1
    for row in get_df(texts_path).itertuples():
        if 'zh' in which_language:
            doc_name, title = str(getattr(row, 'video_id')), getattr(row, 'title')  # get Chinese title line by line
        if 'en' in which_language:
            doc_name, title = str(getattr(row, 'video_id')), getattr(row, 'title_en')  # get English title line by line

        item_name_to_id[str(doc_name)] = item_id
        item_id_to_dic[item_id] = str(doc_name)
        item_id += 1
    return item_id_to_dic, item_name_to_id


def read_text_bert(news_path, args, tokenizer, which_language):
    item_id_to_dic = {}
    item_name_to_id = {}
    item_id = 1
    for row in get_df(news_path).itertuples():
        if 'zh' in which_language:
            doc_name, title = str(getattr(row, 'video_id')), getattr(row, 'title')  # get Chinese title line by line
        if 'en' in which_language:
            doc_name, title = str(getattr(row, 'video_id')), getattr(row, 'title_en')  # get English title line by line

        if 'title' in args.news_attributes:
            title = tokenizer(title.lower(), max_length=args.num_words_title, padding='max_length', truncation=True)
        else:
            title = []

        if 'abstract' in args.news_attributes:
            abstract = tokenizer(abstract.lower(), max_length=args.num_words_abstract, padding='max_length', truncation=True)
        else:
            abstract = []

        if 'body' in args.news_attributes:
            body = tokenizer(body.lower()[:2000], max_length=args.num_words_body, padding='max_length', truncation=True)
        else:
            body = []
        item_name_to_id[doc_name] = item_id
        item_id_to_dic[item_id] = [title, abstract, body]
        item_id += 1
    return item_id_to_dic, item_name_to_id


def read_behaviors(behaviors_path, before_item_id_to_dic, before_item_name_to_id, max_seq_len, min_seq_len, Log_file):
    Log_file.info("##### news number {} {} (before clearing)#####".format(len(before_item_id_to_dic),
                                                                          len(before_item_name_to_id)))
    Log_file.info("##### min seq len {} #####".format(min_seq_len))
    before_item_num = len(before_item_name_to_id)
    before_item_counts = [0] * (before_item_num + 1)
    user_seq_dic = {}
    seq_num = 0
    before_seq_num = 0

    Log_file.info('rebuild user seqs...')
    with open(behaviors_path, "r") as f:
        for line in f:
            splited = line.strip('\n').split('\t')
            before_seq_num += 1
            user_name = splited[0]
            history_item_name = splited[1].split(' ')
            if len(history_item_name) < min_seq_len:
                continue
            history_item_name = history_item_name[-(max_seq_len+2):]  # 和ber4rec统一
            item_ids_sub_seq = [before_item_name_to_id[i] for i in history_item_name]  # name seq -> id seq
            user_seq_dic[user_name] = item_ids_sub_seq  # 只记录seq长度符合要求的 user-seq pairs
            for item_id in item_ids_sub_seq:
                before_item_counts[item_id] += 1  # 不记录一些过短的序列中的item，导致一些item记0
            seq_num += 1
    Log_file.info("##### user seqs before {}".format(before_seq_num))

    item_id = 1  # 删掉一些短的seq-->损失一些item-->给item重新编号，并对应其 token seq
    item_id_to_content = {}
    item_id_before_to_now = {}
    for before_item_id in range(1, before_item_num + 1):
        if before_item_counts[before_item_id] != 0:
            item_id_before_to_now[before_item_id] = item_id  # 对不记0的item重新赋id
            item_id_to_content[item_id] = before_item_id_to_dic[before_item_id]  # 重新赋的id，对应到该不记0位置的dict
            item_id += 1
    item_num = len(item_id_before_to_now)
    Log_file.info("##### items after clearing {}, {}#####".format(item_num, len(item_id_to_content)))

    users_train = {}
    users_valid = {}
    users_history_for_valid = {}
    users_history_for_test = {}

    train_pairs = []
    valid_pairs = []
    test_pairs = []

    user_id = 1  # 对重新编号item的长 user seq 赋 user id
    for user_name, item_seqs in user_seq_dic.items():
        user_seq = [item_id_before_to_now[i] for i in item_seqs]  # 原来的id seq -> 现在的id seq
        train = user_seq[:-2]
        valid = user_seq[:-1]
        users_train[user_id] = train
        users_valid[user_id] = valid

        users_history_for_valid[user_id] = torch.LongTensor(np.array(train))
        users_history_for_test[user_id] = torch.LongTensor(np.array(valid))

        valid_target = valid[-1]
        test_target = user_seq[-1]
        for i in train:
            train_pairs.append((user_id, i))  # [(1, 31), (1, 32), (1, 33), ..., (1, 48), (2, 11), (2, 12), ...]
        valid_pairs.append((user_id, valid_target))  # [(1, 49), (2, 29), (3, 9), ...]
        test_pairs.append((user_id, test_target))  # [(1, 50), (2, 30), (3, 10), ...]
        user_id += 1

    user_num = len(user_seq_dic)
    Log_file.info("##### user seqs after clearing {}, {}, {}, {} #####".
                  format(seq_num, len(user_seq_dic), len(users_train), len(users_valid)))
    Log_file.info("##### train pairs {} #####".format(len(train_pairs)))
    Log_file.info("##### validation pairs {} #####".format(len(valid_pairs)))
    Log_file.info("##### test pairs {} #####".format(len(test_pairs)))

    return user_num, item_num, item_id_to_content, users_train, users_valid, \
        np.array(train_pairs), np.array(valid_pairs), np.array(test_pairs), \
        users_history_for_valid, users_history_for_test


'''
    users_train: {
        1: [31, 32, 33, ..., 48],
        2: [11, 12, 13, ..., 28],
        3: [1, 2, 3, ..., 8],
        ...
    }
    users_valid: {
        1: [31, 32, 33, ..., 48, 49],
        2: [11, 12, 13, ..., 28, 29],
        3: [1, 2, 3, ..., 8, 9],
        ...
    }
'''


def get_doc_input_bert(item_id_to_content, args):
    item_num = len(item_id_to_content) + 1

    if 'title' in args.news_attributes:
        news_title = np.zeros((item_num, args.num_words_title), dtype='int32')  # 二维ndarray
        news_title_attmask = np.zeros((item_num, args.num_words_title), dtype='int32')  # 二维ndarray
    else:
        news_title = None
        news_title_attmask = None

    if 'abstract' in args.news_attributes:
        news_abstract = np.zeros((item_num, args.num_words_abstract), dtype='int32')
        news_abstract_attmask = np.zeros((item_num, args.num_words_abstract), dtype='int32')
    else:
        news_abstract = None
        news_abstract_attmask = None

    if 'body' in args.news_attributes:
        news_body = np.zeros((item_num, args.num_words_body), dtype='int32')
        news_body_attmask = np.zeros((item_num, args.num_words_body), dtype='int32')
    else:
        news_body = None
        news_body_attmask = None

    for item_id in range(1, item_num):
        title, abstract, body = item_id_to_content[item_id]

        if 'title' in args.news_attributes:
            news_title[item_id] = title['input_ids']
            news_title_attmask[item_id] = title['attention_mask']

        if 'abstract' in args.news_attributes:
            news_abstract[item_id] = abstract['input_ids']
            news_abstract_attmask[item_id] = abstract['attention_mask']

        if 'body' in args.news_attributes:
            news_body[item_id] = body['input_ids']
            news_body_attmask[item_id] = body['attention_mask']

    return news_title, news_title_attmask, \
        news_abstract, news_abstract_attmask, \
        news_body, news_body_attmask
