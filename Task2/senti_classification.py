import os
import sys
import argparse
import random
import nltk
from nltk.corpus import stopwords
from gensim.models import Word2Vec
import numpy as np
import pandas as pd       
import pickle
import json


from tools import *

CLASS_NUM = 3
LOG_NAME = None

# 设置 GPU 按需增长
# config = tf.ConfigProto(log_device_placement=True)
config = tf.ConfigProto()
config.gpu_options.allow_growth = True
sess = tf.InteractiveSession(config=config)

# init parameter #
# ########################################################### #
batch_size = tf.placeholder(tf.int32, [])

# The dim of voc: 10000, 30000, 50000, 500
input_size = 10000

# learningrate
learningrate = tf.placeholder(tf.float32, [])

X = tf.placeholder(tf.float32, [None, input_size])
y = tf.placeholder(tf.float32, [None, CLASS_NUM])

# train the model #
# ########################################################### #
W = tf.Variable(tf.random_uniform([input_size, CLASS_NUM]), dtype=tf.float32)
bias = tf.Variable(tf.constant(0.1, shape=[CLASS_NUM]), dtype=tf.float32)
y_pre = tf.nn.softmax(tf.matmul(input_size, W) + bias)

# loss function
cross_entropy = -tf.reduce_mean(y * tf.log(y_pre))
train_op = tf.train.GradientDescentOptimizer(learningrate).minimize(cross_entropy)

correct_prediction = tf.equal(tf.argmax(y_pre, 1), tf.argmax(y, 1))
accuracy = tf.reduce_mean(tf.cast(correct_prediction, 'float'))

saver = tf.train.Saver()
sess.run(tf.global_variables_initializer())

# read train.tsv and split into train and valid
def load_train():
    pd_lines = pd.read_csv("train.tsv", header=0, delimiter="\t", quoting=3)
    lines = zip(pd_lines['Phrase'], pd_lines['Sentiment'])
    random.shuffle(lines)
    size = len(lines)
    trainset = lines[:int(0.9 * size)]
    validset = lines[int(0.9 * size):]
    return trainset, validset

# read test.tsv
def load_test():
    pd_lines = pd.read_csv("test.tsv", header=0, delimiter="\t", quoting=3)
    testset = zip(pd_lines['Phrase'], pd_lines['Sentiment'])
    return testset
    
# input:
#    trainset: zip tuple
#     feature: int
def get_voc(trainset, feature):
    phrase, sentiment = zip(*trainset)
    text = ' '.join(phrase)
    stop = set(stopwords.words('english'))
    Voc = []
    if feature == 1:
        fdist = nltk.FreqDist(text.split(' '))
        sorted_voc = fdist.most_common()
        voc_without_stop = [w for w,_ in sorted_voc if w not in stop]
        Voc = voc_without_stop[:10000]
    elif feature == 2:
        bigrams = []
        for i in range(len(phrase)):
            origin = list(nltk.bigrams(phrase[i].split(' ')))
            clean = [(a, b) for (a, b) in origin if a.isalpha() and b.isalpha()
                    and (a not in stop or b not in stop)]
            bigrams.extend(clean)
        fdist = nltk.FreqDist(bigrams)
        sorted_bigram = fdist.most_common()
        bigram_clean = [bi for bi,_ in sorted_bigram]
        Voc = bigram_clean[:30000]
    elif feature == 3:
        trigrams = []
        for i in range(len(phrase)):
            origin = list(nltk.trigrams(phrase[i].split(' ')))
            clean = [(a, b, c) for (a, b, c) in origin if 
                        a.isalpha() and b.isalpha() and c.isalpha() and 
                        (a not in stop or b not in stop or c not in stop)]
            trigrams.extend(clean)
        fdist = nltk.FreqDist(trigrams)
        sorted_trigram = fdist.most_common()
        trigram_clean = [bi for bi,_ in sorted_trigram]
        Voc = trigram_clean[:50000]
    else:
        print "Unkown feature type!"
        sys.exit(1)
    ngram_to_ix = { ch:i for i,ch in enumerate(Voc) }
    return ngram_to_ix
    
# input:
#    str: word string
#     feature: int
#    ngram_to_ix: dict
def generate_feature(str, feature, ngram_to_ix):
    words = str.split(' ')
    if feature < 4:
        Vocsize = len(ngram_to_ix)
        vec = [0] * Vocsize
    else:
        n_dim = ngram_to_ix[0]
        vec = np.zeros(n_dim).reshape((1, n_dim))
        
    if(feature == 1):
        for i in range(len(words)):
            if words[i] in ngram_to_ix:
                vec[ngram_to_ix[words[i]]] += 1
    elif(feature == 2):
        bigram = list(nltk.bigrams(words))
        for i in range(len(bigram)):
            if bigram[i] in ngram_to_ix:
                vec[ngram_to_ix[bigram[i]]] += 1
    elif(feature == 3):
        trigram = list(nltk.trigrams(words))
        for i in range(len(trigram)):
            if trigram[i] in ngram_to_ix:
                vec[ngram_to_ix[trigram[i]]] += 1
    elif(feature == 4):
        imdb_w2v = ngram_to_ix[1]
        count = 0
        for i in range(len(words)):
            try:
                vec += imdb_w2v[words[i].lower()].reshape((1, n_dim))
                count += 1
            except KeyError:
                continue
        if count != 0:
            vec /= count
        return vec[0]
    else:
        print "Unkown feature type!"
        sys.exit(1)
    return np.array(vec)
    

def generate_label(level):
    label = [0] * CLASS_NUM
    if level < 2:
        label[0] = 1
    else if level > 2:
        label[2] = 1
    else:
        label[1] = 1
    return np.array(label)
    
def evaluate(y, p, F = 0):    
    trueLabel = np.argmax(y, 1)
    predLabel = np.argmax(p, 1)
    with open(LOG_NAME, 'a') as f:
        print >> f, "  trueLabel:", trueLabel
        print >> f, "  predLabel:", predLabel
    accu = eval_accu(trueLabel, predLabel)
    if F == 1:
        eval = eval_F(trueLabel, predLabel)
        return accu, eval
    return accu
    
# input:
#    X, y: np.array
#    model: class Model
def train_model(trainset, batch_size, feature, ngram_to_ix, learning_rate):
    m = len(trainset)
    phrase, sentiment = zip(*trainset)
    for iter in range(m / batch_size - 1):
        batch_X = np.array([generate_feature(str, feature, ngram_to_ix) \
                        for str in phrase[iter * batch_size : (iter+1) * batch_size]])
        batch_y = np.array([generate_label(level) \
                        for level in sentiment[iter * batch_size : (iter+1) * batch_size]])
        
        sess.run(train_op, feed_dict={X:batch_X, y:batch_y, batch_size:batch_size, learningrate:learning_rate})
        p = sess.run(y_pre, feed_dict={X:batch_X, batch_size:batch_size})
        train_loss = sess.run(cross_entropy, feed_dict={X:batch_X, y:batch_y, batch_size:batch_size})
        if iter % 100 == 0:
            train_accu = evaluate(batch_y, p)
            with open(LOG_NAME, 'a') as f:
                print >> f, "iter %d: training loss %f, training accu %f\n" % (iter, train_loss, train_accu)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('-f', metavar='feature', type = int, choices=[1,2,3,4], help="1 for bag-of-word, 2 for bigram, 3 for trigram, 4 for word2vec", default=1)
    parser.add_argument('-l', metavar='learning', type = float, default=0.01)
    parser.add_argument('-e', metavar='reg', type = float, default=0.01)
    args = parser.parse_args()
    print "feature %d, learning %.02f, reg %.02f" % (args.f, args.l, args.e)
    LOG_NAME = 'train_f%d_l%.2f_e%.2f.log' % (args.f, args.l, args.e)
    with open(LOG_NAME, 'w') as f:
        print >> f, "Logging"
    
    trainset, validset = load_train()
    print "trainset length: %d, validset length: %d" % (len(trainset), len(validset))
    
    if(args.f < 4):
        print "Generating Voc..."
        if not os.path.exists("cache/ngram_f%d.pickle" % args.f):
            print "  Saving new ngram_to_ix..."
            ngram_to_ix = get_voc(trainset, args.f)
            with open("cache/ngram_f%d.pickle" % args.f, 'w') as f:
                pickle.dump(ngram_to_ix, f)
        else:
            print "  Loading original ngram_to_ix..."
            with open("cache/ngram_f%d.pickle" % args.f, 'r') as f:
                ngram_to_ix = pickle.load(f)
        n = len(ngram_to_ix)
    else:
        print "Generating Word2Vec..."
        n_dim = 500
        if not os.path.exists('w2v/imdb_w2v'):
            print "  Saving new Word2Vec..."
            phrase, sentiment = zip(*trainset)
            x_train = []
            for i in range(len(phrase)):
                x_train.append(phrase[i].lower().split())
            imdb_w2v = Word2Vec(x_train, size=n_dim, min_count=1)
            imdb_w2v.save("w2v/imdb_w2v")
            imdb_w2v.wv.save_word2vec_format("w2v/word2vec_org",
                                              "w2v/vocabulary",
                                              binary=False)
        else:
            print "  Loading original Word2Vec..."
            imdb_w2v = Word2Vec.load('w2v/imdb_w2v')
        ngram_to_ix = (n_dim, imdb_w2v)
        n = n_dim
        
    
    # X and y
    print "Generating valid features..."    
    phrase, sentiment = zip(*validset)
    valid_X = np.array([generate_feature(str, args.f, ngram_to_ix) for str in phrase])
    valid_y = np.array([generate_label(level) for level in sentiment])
    valid_batch_size = len(valid_X) - len(valid_X) % timestep_size
    
    
    # model parameters
    m = len(trainset)
    k = CLASS_NUM
    batch_size = 120
    model = Model(n, k, args.e, args.l)
    
    max_accu = 0.0
    min_loss = 5
    turn = 0
    print "Training begin..."
    for epoch in range(200):
        train_model(trainset, batch_size, args.f, ngram_to_ix, args.l)
        valid_p = sess.run(y_pre, feed_dict={_X:valid_X[:valid_batch_size], batch_size:valid_batch_size, keep_prob:1})
        loss = sess.run(cross_entropy, feed_dict={_X:valid_X[:valid_batch_size], y:valid_y[:valid_batch_size], keep_prob:1, batch_size:valid_batch_size})
        accu, more_eval = evaluate(valid_y, valid_p, 1)
        with open(LOG_NAME, 'a') as f:
            print >> f, "epoch %d: valid loss %f, valid accu %f" % (epoch, loss, accu)
            print >> f, "-------------------------------------\n"
        print "epoch %d: valid loss %f, valid accu %f" % (epoch, loss, accu)
        print more_eval
        print "-------------------------------------"
        if min_loss - loss > 1e-6:
            min_loss = loss
            saver_path = saver.save(sess, 'save/f%d_l%.2f_e%.2f_epoch%d.ckpt' % (args.f, args.l, args.e, epoch))
            print "Minloss update, Model saved in file:", saver_path
            turn = 0
        else:
            turn += 1
        print "min_loss:%f, turn: %d" % (min_loss, turn) 
        if turn == 10:
            print "Early stop!"
            break;
    
    print "Training End!"
    saver_path = saver.save(sess, 'save/model.ckpt')
    print "Model saved in file:", saver_path
    
    with open(LOG_NAME, 'a') as f:
        print >> f, "****************************"
        print >> f, "Testing in validset begin..."
        saver.restore(sess,'save/model.ckpt')
        valid_p = sess.run(y_pre, feed_dict={_X:valid_X[:valid_batch_size], batch_size:valid_batch_size, keep_prob:1})
        loss = sess.run(cross_entropy, feed_dict={_X:valid_X[:valid_batch_size], y:valid_y[:valid_batch_size], keep_prob:1, batch_size:valid_batch_size})
        accu, more_eval = evaluate(valid_y, valid_p, 1)
        print >> f, "Loss %f, Accu %f" % (loss, accu)
        print >> f, more_eval
        print >> f, "Testing End!"
        
    sess.close()
    
    
    
    
            
    
        
        
        
    
    
    
    
    
    
    
    
    

