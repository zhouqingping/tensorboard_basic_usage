# ==============================================================================
import os
import shutil
import tensorflow as tf
from cifar10_read import read_dataset
from cifar10_read import data_augumentation

LOGBASE = r'.\tf_log_final'
if  os.path.exists(LOGBASE):
    shutil.rmtree(LOGBASE)
os.makedirs(LOGBASE)

datadir = 'cifar10_data'
cifar10 = read_dataset(datadir, onehot_encoding=True)

def conv_layer(input, k,s,channels_in, channels_out, name="conv"):
    with tf.name_scope(name):
        w = tf.Variable(tf.truncated_normal([k, k, channels_in, channels_out], stddev=0.05), name="W")
        b = tf.Variable(tf.constant(0.1, shape=[channels_out]), name="b")
        conv = tf.nn.conv2d(input, w, strides=[1, s, s, 1], padding="SAME")
        act = tf.nn.relu(conv + b)
        tf.summary.histogram("weights", w)
        tf.summary.histogram("biases", b)
        tf.summary.histogram("activations", act)
        return act

def pool_layer(input,k,s,name='pooling'):
    with tf.name_scope(name):
        return tf.nn.max_pool(input, ksize=[1, k, k, 1],
                              strides=[1, s, s, 1], padding="SAME")

def fc_layer(input, size_in, size_out, name="fc",reg=False):
    with tf.name_scope(name):
          w = tf.Variable(tf.truncated_normal([size_in, size_out], stddev=0.1), name="W")
          b = tf.Variable(tf.constant(0.1, shape=[size_out]), name="b")
          preact = tf.matmul(input, w) + b
          tf.summary.histogram("weights", w)
          tf.summary.histogram("biases", b)
          tf.summary.histogram("activations", preact)

          if reg:
              weight_l2_loss = 0.001*tf.nn.l2_loss(w)
              tf.add_to_collection('lossess',weight_l2_loss)
          return preact


def mnist_model(learning_rate,use_l2_loss,use_three_conv,use_data_aug,LOGBASE,hparam):
    tf.reset_default_graph()
    sess = tf.Session()
    keep_prob = tf.placeholder(tf.float32)
    # Setup placeholders, and reshape the data
    with tf.name_scope('images_labels'):
        with tf.name_scope('input'):
            x = tf.placeholder(tf.float32, shape=[None, 32*32*3], name="images_x")
            y = tf.placeholder(tf.float32, shape=[None, 3], name="labels_y")
        with tf.name_scope('input_images'):
            x_image = tf.transpose(tf.reshape(x, [-1, 3, 32, 32]), perm=[0, 2, 3, 1])
            x_image = tf.image.convert_image_dtype(x_image, tf.float32)
            tf.summary.image('images', x_image, max_outputs=5)
            if use_data_aug :
                # ~~~~~~
                x_image = tf.cond(keep_prob<1,lambda:data_augumentation(x_image),lambda:x_image)
                tf.summary.image('aug_images',x_image, max_outputs=5)

    if use_three_conv:
        conv1 = conv_layer(x_image,k=3,s=1,channels_in=3, channels_out=16, name="conv1")
        # norm2 = tf.nn.lrn(conv2, 4, bias=1.0, alpha=0.001 / 9.0, beta=0.75, name='norm2')
        pool1 = pool_layer(conv1, k=2, s=2, name='pooling1')

        conv2 = conv_layer(pool1, k=3,s=1,channels_in=16, channels_out=20, name="conv2")
        pool2 = pool_layer(conv2, k=2, s=2, name='pooling2')

        conv3 = conv_layer(pool2, k=3, s=1, channels_in=20, channels_out=20, name="conv3")
        conv_out = pool_layer(conv3, k=2, s=2, name='pooling3')
    else:
        conv1 = conv_layer(x_image, k=3, s=1, channels_in=3, channels_out=64, name="conv1")
        conv_out = pool_layer(conv1, k=2,s=2, name="pooling1")

    size = conv_out.get_shape().as_list()
    length = size[-1]*size[-2]*size[-3]

    with tf.name_scope('flatten'):
         flattened = tf.reshape(conv_out, [-1, length])

    if use_l2_loss:
        fc1 = fc_layer(flattened, length, 512, "fc1",reg=True)
        relu1 = tf.nn.relu(fc1)
        drop_out1 = tf.nn.dropout(relu1, keep_prob=keep_prob)
        tf.summary.histogram("fc2/drop_out1", drop_out1)

        logits = fc_layer(drop_out1, 512, 3, "output")
    else:
        logits = fc_layer(flattened, length, 3, "output",reg=False)

    with tf.name_scope("loss"):
        cross_entropy_mean = tf.reduce_mean(tf.nn.softmax_cross_entropy_with_logits(
                logits=logits, labels=y), name="cross_entropy_mean")
        tf.add_to_collection('losses',cross_entropy_mean)
        loss = tf.add_n(tf.get_collection('losses'),name='total_loss')
        tf.summary.scalar("loss", loss)

    with tf.name_scope("train"):
        train_step = tf.train.AdamOptimizer(learning_rate).minimize(loss)

    with tf.name_scope("accuracy"):
        correct_prediction = tf.equal(tf.argmax(logits, 1), tf.argmax(y, 1))
        accuracy = tf.reduce_mean(tf.cast(correct_prediction, tf.float32))
        tf.summary.scalar("accuracy", accuracy)

    merged_summary = tf.summary.merge_all()
    saver = tf.train.Saver()
    train_writer = tf.summary.FileWriter(os.path.join(LOGBASE, hparam, 'train'), graph=sess.graph)
    test_writer = tf.summary.FileWriter(os.path.join(LOGBASE, hparam, 'test'))

    sess.run(tf.global_variables_initializer())
    for i in range(500):
        batch_x, batch_y = cifar10.train.next_batch(32)
        if i%20 == 0:
            valid_x,valid_y = cifar10.valid.images, cifar10.valid.labels
            summary,acc = sess.run([merged_summary,accuracy],
                                   feed_dict={x: valid_x, y: valid_y,keep_prob:1})
            test_writer.add_summary(summary,i)
            print('Accuracy at step {}: {}'.format(i,acc))
        else:
            if i%100 == 0:
                run_options = tf.RunOptions(trace_level=tf.RunOptions.FULL_TRACE)
                run_metadata = tf.RunMetadata()
                _, summary,lss,acc = sess.run([train_step, merged_summary,loss,accuracy],
                                               feed_dict={x: batch_x, y: batch_y,keep_prob:0.5},
                                               options=run_options,
                                               run_metadata=run_metadata
                                               )
                train_writer.add_summary(summary,global_step=i)
                train_writer.add_run_metadata(run_metadata, 'step{}'.format(i))
            else:
               _,summary =  sess.run([train_step, merged_summary],
                                     feed_dict={x: batch_x, y: batch_y,keep_prob:0.5})
               train_writer.add_summary(summary,i)

    saver.save(sess, os.path.join(LOGBASE,hparam,"model.ckpt"))
    train_writer.close()
    test_writer.close()
    sess.close()

def make_hparam_string(learning_rate, use_l2_loss, use_three_conv,use_data_aug):
    conv_param = "conv=3" if use_three_conv else "conv=1"
    reg_param = "reg=l2" if use_l2_loss else "reg=no"
    data_param = 'aug=yes' if use_data_aug else "aug=no"
    return "lr_%.0E,%s,%s,%s" % (learning_rate, conv_param, reg_param,data_param)

def main():
   for learning_rate in [0.01,0.001,0.0001]:
        for use_l2_loss in [True]:
            for use_three_conv in [True]:
                 for use_data_aug in [False,True]:
                     hparam = make_hparam_string(learning_rate,use_l2_loss,use_three_conv,use_data_aug)
                     print('---------------------------------------------------')
                     print('Starting run for %s' % hparam)
                     print('---------------------------------------------------')
                     mnist_model(learning_rate, use_l2_loss,use_three_conv,use_data_aug,LOGBASE,hparam)
   print('Done training!')
   print('Run `tensorboard --LOGBASE=%s` to see the results.'% LOGBASE)

if __name__ == '__main__':
  main()

